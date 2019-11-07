"""Support for functionality to have conversations with Home Assistant."""
import logging
import re

import voluptuous as vol

from homeassistant import core
from homeassistant.components import http, websocket_api
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.loader import bind_hass

from .agent import AbstractConversationAgent
from .default_agent import async_register, DefaultAgent

_LOGGER = logging.getLogger(__name__)

ATTR_TEXT = "text"

DOMAIN = "conversation"

REGEX_TYPE = type(re.compile(""))
DATA_AGENT = "conversation_agent"

SERVICE_PROCESS = "process"

SERVICE_PROCESS_SCHEMA = vol.Schema({vol.Required(ATTR_TEXT): cv.string})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional("intents"): vol.Schema(
                    {cv.string: vol.All(cv.ensure_list, [cv.string])}
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

WS_TYPE_GET_ONBOARDING = "conversation/onboarding/get"
WS_TYPE_SET_ONBOARDING = "conversation/onboarding/set"
WS_TYPE_GET_ATTRIBUTION = "conversation/attribution"

SCHEMA_GET_ONBOARDING = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_GET_ONBOARDING}
)

SCHEMA_SET_ONBOARDING = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_SET_ONBOARDING, vol.Required("data"): dict}
)

SCHEMA_GET_ATTRIBUTION = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
    {vol.Required("type"): WS_TYPE_GET_ATTRIBUTION}
)

async_register = bind_hass(async_register)  # pylint: disable=invalid-name


@core.callback
@bind_hass
def async_set_agent(hass: core.HomeAssistant, agent: AbstractConversationAgent):
    """Set the agent to handle the conversations."""
    hass.data[DATA_AGENT] = agent


async def async_setup(hass, config):
    """Register the process service."""

    async def process(hass, text):
        """Process a line of text."""
        agent = hass.data.get(DATA_AGENT)

        if agent is None:
            agent = hass.data[DATA_AGENT] = DefaultAgent(hass)
            await agent.async_initialize(config)

        return await agent.async_process(text)

    async def handle_service(service):
        """Parse text into commands."""
        text = service.data[ATTR_TEXT]
        _LOGGER.debug("Processing: <%s>", text)
        try:
            await process(hass, text)
        except intent.IntentHandleError as err:
            _LOGGER.error("Error processing %s: %s", text, err)

    @websocket_api.async_response
    async def websocket_get_onboarding(hass, connection, msg):
        """Do we need onboarding."""
        agent = hass.data.get(DATA_AGENT)

        if agent is None:
            agent = hass.data[DATA_AGENT] = DefaultAgent(hass)
            await agent.async_initialize(config)
        connection.send_result(msg["id"], await agent.async_get_onboarding())

    @websocket_api.async_response
    async def websocket_set_onboarding(hass, connection, msg):
        """Set onboarding status."""
        agent = hass.data.get(DATA_AGENT)

        if agent is None:
            agent = hass.data[DATA_AGENT] = DefaultAgent(hass)
            await agent.async_initialize(config)

        success = await agent.async_set_onboarding(msg.get("data"))

        if success:
            connection.send_result(msg["id"])
        else:
            connection.send_error(msg["id"])

    @websocket_api.async_response
    async def websocket_get_attribution(hass, connection, msg):
        """Get attribution data."""
        agent = hass.data.get(DATA_AGENT)

        if agent is None:
            agent = hass.data[DATA_AGENT] = DefaultAgent(hass)
            await agent.async_initialize(config)

        connection.send_result(msg["id"], agent.attribution)

    hass.services.async_register(
        DOMAIN, SERVICE_PROCESS, handle_service, schema=SERVICE_PROCESS_SCHEMA
    )

    hass.http.register_view(ConversationProcessView(process))

    hass.components.websocket_api.async_register_command(
        WS_TYPE_GET_ATTRIBUTION, websocket_get_attribution, SCHEMA_GET_ATTRIBUTION
    )

    hass.components.websocket_api.async_register_command(
        WS_TYPE_GET_ONBOARDING, websocket_get_onboarding, SCHEMA_GET_ONBOARDING
    )

    hass.components.websocket_api.async_register_command(
        WS_TYPE_SET_ONBOARDING, websocket_set_onboarding, SCHEMA_SET_ONBOARDING
    )

    return True


class ConversationProcessView(http.HomeAssistantView):
    """View to retrieve shopping list content."""

    url = "/api/conversation/process"
    name = "api:conversation:process"

    def __init__(self, process):
        """Initialize the conversation process view."""
        self._process = process

    @RequestDataValidator(vol.Schema({vol.Required("text"): str}))
    async def post(self, request, data):
        """Send a request for processing."""
        hass = request.app["hass"]

        try:
            intent_result = await self._process(hass, data["text"])
        except intent.IntentHandleError as err:
            intent_result = intent.IntentResponse()
            intent_result.async_set_speech(str(err))

        if intent_result is None:
            intent_result = intent.IntentResponse()
            intent_result.async_set_speech("Sorry, I didn't understand that")

        return self.json(intent_result)
