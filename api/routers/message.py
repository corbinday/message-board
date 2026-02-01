import base64
import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response

from api.dependencies import Client
import api.queries as q

router = APIRouter()
logger = logging.getLogger(__name__)

EXPECTED_PAYLOAD_SIZE = 32 * 32 * 3


def get_templates(request: Request):
    return request.app.state.templates


def get_context(request: Request, **kwargs):
    return request.app.state.get_template_context(request, **kwargs)


@router.get("/paint", response_class=HTMLResponse, name="message.paint")
async def paint(request: Request):
    templates = get_templates(request)
    context = get_context(request, BOARD_WIDTH=32, BOARD_HEIGHT=32)
    return templates.TemplateResponse("paint/canvas.html", context)


@router.post("/save_canvas", name="message.save_painting")
async def save_painting(
    request: Request,
    client: Client,
    pixel_data: str = Form(None),
):
    """
    Receives Base64 encoded pixel data from the painting canvas,
    decodes it, validates it, and saves it as a new message in Gel/EdgeDB.
    """
    # 1. Get the Base64 string from the form data
    base64_string = pixel_data

    if not base64_string:
        logger.error("API Error: No pixel data received.")
        return JSONResponse({"error": "No pixel data received"}, status_code=400)

    # --- CRITICAL DEBUGGING STEP 1: Incoming Base64 String Check ---
    logger.info("--- Canvas Save Attempt ---")
    logger.info(f"Received Base64 string length: {len(base64_string)}")
    # Log the first/last characters to ensure data isn't empty or truncated
    logger.info(f"Base64 prefix: {base64_string[:30]}... suffix: {base64_string[-30:]}")
    # -------------------------------------------------------------

    # 2. Decode the Base64 string
    try:
        raw_binary_data = base64.b64decode(base64_string)

        # --- CRITICAL DEBUGGING STEP 2: Decoded Data Check ---
        logger.info(f"Decoded data size: {len(raw_binary_data)} bytes")
        # Log the first 50 bytes of the decoded data.
        # If this is b'\x00\x00\x00...', the client-side encoding failed.
        logger.info(f"Decoded data prefix (first 50 bytes): {raw_binary_data[:50]}")
        # -----------------------------------------------------

    except base64.binascii.Error as e:
        logger.error(f"API Error: Invalid Base64 encoding. Exception: {e}")
        return JSONResponse({"error": "Invalid data format"}, status_code=400)

    # 3. Validation Check
    if len(raw_binary_data) != EXPECTED_PAYLOAD_SIZE:
        logger.error(
            f"API Error: Incorrect payload size. Expected {EXPECTED_PAYLOAD_SIZE}, got {len(raw_binary_data)}."
        )
        return JSONResponse({"error": "Data size mismatch. Expected 32x32 RGB data."}, status_code=400)

    # 4. Save the Message to EdgeDB
    try:
        result = await q.insertMessage(
            client,
            data=raw_binary_data,
            size="Galactic",  # 32x32 canvas
            recipient_id=None,  # No recipient for now
        )

        # Log successful insertion
        logger.info(f"Message successfully inserted into EdgeDB with ID: {result.id}")

        # HTMX Success Response
        return Response(content="Message sent successfully!", status_code=200)

    except Exception as e:
        logger.error(f"Database Query Error while saving message: {e}")
        return JSONResponse({"error": "Internal server error during database save."}, status_code=500)


@router.get("/get_canvas", name="message.get_canvas")
async def get_canvas(client: Client):
    # 1. Fetch the latest message data
    try:
        message = await q.selectLatestMessage(client)
    except Exception as e:
        print(f"EdgeDB query error: {e}")
        # Return a server error if the database query fails
        return JSONResponse({"error": "Database query failed"}, status_code=500)

    if not message:
        # If no messages exist in the database, return a default/empty response
        # Returning a 204 No Content or a default JSON with an empty field is standard.
        return JSONResponse({"pixel_data_b64": ""}, status_code=200)

    # The data fetched from EdgeDB is a bytes object
    raw_bytes = message.graphic.binary

    # 2. Encode the raw bytes into a Base64 string
    # Python's base64.b64encode returns bytes, so we decode it to a UTF-8 string
    base64_string = base64.b64encode(raw_bytes).decode("utf-8")

    # 3. Wrap the Base64 string in a JSON object with the expected key
    response_data = {"pixel_data_b64": base64_string}

    return JSONResponse(response_data, status_code=200)
