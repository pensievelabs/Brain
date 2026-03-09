import os
from datetime import datetime, timezone
import dateutil.parser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

class CalendarManager:
    """
    Manages interactions with the Google Calendar API.
    Provides tools for LLM use: list_calendars, get_upcoming_events, create_calendar_event.
    """

    def __init__(self, config: Config):
        self.config = config
        self.credentials_path = getattr(config, 'CALENDAR_CREDENTIALS_PATH', os.path.join(config.AGENT_DIR, 'credentials.json'))
        self.token_path = getattr(config, 'CALENDAR_TOKEN_PATH', os.path.join(config.AGENT_DIR, 'token.json'))
        self.service = self._authenticate()

    def _authenticate(self):
        """Load credentials and build the Calendar API service. Fails gracefully if no token."""
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, ["https://www.googleapis.com/auth/calendar"])
            except Exception as e:
                logger.error(f"Failed to load calendar token: {e}")
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(self.token_path, "w") as token:
                        token.write(creds.to_json())
                except Exception as e:
                    logger.error(f"Failed to refresh calendar token: {e}")
                    creds = None
            else:
                logger.warning("Calendar not authenticated. Run auth_calendar.py locally first.")
                return None

        try:
            service = build("calendar", "v3", credentials=creds)
            return service
        except Exception as e:
            logger.error(f"Failed to build Calendar service: {e}")
            return None

    def list_calendars(self) -> str:
        """Fetch all available calendars and return their IDs and summaries."""
        if not self.service:
            return "Calendar API not authenticated."
            
        try:
            calendars_result = self.service.calendarList().list().execute()
            calendars = calendars_result.get('items', [])
            
            if not calendars:
                return "No calendars found."
                
            output = "Available Calendars:\n"
            for cal in calendars:
                name = cal.get('summary', 'Unknown')
                cal_id = cal.get('id', 'Unknown')
                primary = "(Primary)" if cal.get('primary') else ""
                output += f"- {name} {primary} (ID: {cal_id})\n"
                
            return output
        except HttpError as error:
            logger.error(f"An error occurred fetching calendars: {error}")
            return f"An error occurred fetching calendars: {error}"

    def get_upcoming_events(self, max_results: int = 10, calendar_id: str = "primary", time_min: str = None, time_max: str = None) -> str:
        """Get the upcoming N events from the specified calendar, optionally bounded by time."""
        if not self.service:
            return "Calendar API not authenticated."

        try:
            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"
            else:
                try:
                    time_min = dateutil.parser.isoparse(time_min).isoformat()
                except ValueError as e:
                    return f"Error: Invalid time_min format. Details: {e}"

            kwargs = {
                "calendarId": calendar_id,
                "timeMin": time_min,
                "maxResults": int(max_results),
                "singleEvents": True,
                "orderBy": "startTime",
            }
            
            if time_max:
                try:
                    kwargs["timeMax"] = dateutil.parser.isoparse(time_max).isoformat()
                except ValueError as e:
                    return f"Error: Invalid time_max format. Details: {e}"

            events_result = self.service.events().list(**kwargs).execute()
            events = events_result.get("items", [])

            if not events:
                return f"No upcoming events found in calendar '{calendar_id}'."

            output = f"Upcoming {len(events)} events (Calendar ID: {calendar_id}):\n"
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                
                # Try formatting for readability
                try:
                    start_dt = dateutil.parser.isoparse(start)
                    start_str = start_dt.strftime("%Y-%m-%d %H:%M")
                    if "T" not in start: # all day event
                        start_str = start_dt.strftime("%Y-%m-%d (All day)")
                except:
                    start_str = start
                    
                summary = event.get("summary", "No Title")
                output += f"• {start_str}: {summary}\n"
                
            return output

        except HttpError as error:
            logger.error(f"An error occurred fetching events: {error}")
            return f"An error occurred fetching events: {error}"

    def create_calendar_event(self, summary: str, start_time: str, end_time: str, description: str = "", calendar_id: str = "primary") -> str:
        """Create a new event in the specified calendar."""
        if not self.service:
            return "Calendar API not authenticated."

        # Validate/parse time strings to enforce ISO format
        try:
            start_dt = dateutil.parser.isoparse(start_time)
            end_dt = dateutil.parser.isoparse(end_time)
        except ValueError as e:
            return f"Error: Invalid time format. Must be ISO 8601 (e.g. 2026-03-08T15:00:00-07:00). Details: {e}"

        event_body = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
            },
            "end": {
                "dateTime": end_dt.isoformat(),
            },
        }

        try:
            event = self.service.events().insert(calendarId=calendar_id, body=event_body).execute()
            logger.info(f"📅 [Calendar] Event created: {event.get('htmlLink')}")
            return f"Event created successfully: {event.get('htmlLink')}\nSummary: {summary}\nStart: {start_time}"
        except HttpError as error:
            logger.error(f"An error occurred creating the event: {error}")
            return f"An error occurred creating the event: {error}"

    def get_tool_functions(self) -> dict:
        """Returns the tool name → handler mapping for the orchestrator."""
        return {
            "list_calendars": lambda args: self.list_calendars(),
            "get_upcoming_events": lambda args: self.get_upcoming_events(
                args.get("max_results", 10),
                args.get("calendar_id", "primary"),
                args.get("time_min", None),
                args.get("time_max", None)
            ),
            "create_calendar_event": lambda args: self.create_calendar_event(
                args.get("summary", ""),
                args.get("start_time", ""),
                args.get("end_time", ""),
                args.get("description", ""),
                args.get("calendar_id", "primary")
            )
        }

    @staticmethod
    def get_tool_schemas() -> list[dict]:
        """Returns the OpenAI-format tool schemas for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_calendars",
                    "description": "Lists all available Google Calendars for the authenticated user, returning their names and IDs. Use this to find the correct calendar_id to pass to other calendar tools.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_upcoming_events",
                    "description": "Fetches upcoming events from a specific Google Calendar. Can optionally filter by a time range.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of events to return. Default is 10.",
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "The ID of the calendar to fetch from. Pass 'primary' for the main calendar, or a specific ID retrieved via list_calendars.",
                            },
                            "time_min": {
                                "type": "string",
                                "description": "Start time in ISO 8601 format (e.g. '2026-03-08T00:00:00-07:00'). Defaults to current time.",
                            },
                            "time_max": {
                                "type": "string",
                                "description": "End time in ISO 8601 format (e.g. '2026-03-08T23:59:59-07:00'). Optional but highly recommended for day/week specific queries.",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_calendar_event",
                    "description": "Creates a new event on a specific Google Calendar. The times MUST be in ISO 8601 format with timezone offset (e.g. 2026-03-08T15:00:00-07:00).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {
                                "type": "string",
                                "description": "Title or summary of the event.",
                            },
                            "start_time": {
                                "type": "string",
                                "description": "Start time in ISO 8601 format (e.g. '2026-03-08T15:00:00-07:00').",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "End time in ISO 8601 format (e.g. '2026-03-08T16:00:00-07:00').",
                            },
                            "description": {
                                "type": "string",
                                "description": "Optional detailed description of the event.",
                            },
                            "calendar_id": {
                                "type": "string",
                                "description": "The ID of the calendar to create the event in. Pass 'primary' for the main calendar, or a specific ID retrieved via list_calendars.",
                            }
                        },
                        "required": ["summary", "start_time", "end_time"],
                    },
                },
            },
        ]
