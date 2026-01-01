import base64
from flask import (
    current_app,
    g,
    Blueprint,
    render_template,
    request,
    jsonify,
    make_response,
)

import api.queries as q

bp = Blueprint("message", __name__, template_folder="templates")

EXPECTED_PAYLOAD_SIZE = 32 * 32 * 3


@bp.route("/paint")
def paint():
    if request.method == "GET":
        return render_template("paint/canvas.html", BOARD_WIDTH=32, BOARD_HEIGHT=32)


@bp.route("/save_canvas", methods=["POST"])
def save_painting():
    """
    Receives Base64 encoded pixel data from the painting canvas,
    decodes it, validates it, and saves it as a new message in Gel/EdgeDB.
    """
    # 1. Get the Base64 string from the form data
    # Note: HTMX usually sends data via form data (application/x-www-form-urlencoded)
    base64_string = request.form.get("pixel_data")

    if not base64_string:
        current_app.logger.error("API Error: No pixel data received.")
        return jsonify({"error": "No pixel data received"}), 400

    # --- CRITICAL DEBUGGING STEP 1: Incoming Base64 String Check ---
    current_app.logger.info(f"--- Canvas Save Attempt ---")
    current_app.logger.info(f"Received Base64 string length: {len(base64_string)}")
    # Log the first/last characters to ensure data isn't empty or truncated
    current_app.logger.info(
        f"Base64 prefix: {base64_string[:30]}... suffix: {base64_string[-30:]}"
    )
    # -------------------------------------------------------------

    # 2. Decode the Base64 string
    try:
        raw_binary_data = base64.b64decode(base64_string)

        # --- CRITICAL DEBUGGING STEP 2: Decoded Data Check ---
        current_app.logger.info(f"Decoded data size: {len(raw_binary_data)} bytes")
        # Log the first 50 bytes of the decoded data.
        # If this is b'\x00\x00\x00...', the client-side encoding failed.
        current_app.logger.info(
            f"Decoded data prefix (first 50 bytes): {raw_binary_data[:50]}"
        )
        # -----------------------------------------------------

    except base64.binascii.Error as e:
        current_app.logger.error(f"API Error: Invalid Base64 encoding. Exception: {e}")
        return jsonify({"error": "Invalid data format"}), 400

    # 3. Validation Check
    if len(raw_binary_data) != EXPECTED_PAYLOAD_SIZE:
        current_app.logger.error(
            f"API Error: Incorrect payload size. Expected {EXPECTED_PAYLOAD_SIZE}, got {len(raw_binary_data)}."
        )
        return jsonify({"error": "Data size mismatch. Expected 32x32 RGB data."}), 400

    # 4. Save the Message to EdgeDB
    try:
        # Assuming g.client is correctly set up for database transactions
        result = g.client.query_single(
            """
            INSERT Message {
                payload := <bytes>$data,
            }
            """,
            data=raw_binary_data,
        )

        # Log successful insertion
        current_app.logger.info(
            f"Message successfully inserted into EdgeDB with ID: {result.id}"
        )

        # HTMX Success Response
        return make_response("Message sent successfully!", 200)

    except Exception as e:
        current_app.logger.error(f"Database Query Error while saving message: {e}")
        return jsonify({"error": "Internal server error during database save."}), 500


@bp.route("/get_canvas", methods=["GET"])
def get_canvas():
    # 1. Fetch the latest message data
    try:
        # Assuming you fetch the latest message, sorting by created_at descending
        message = g.client.query_single(
            """
            select Message { payload }
            order by .created_at desc
            limit 1;
            """
        )
    except Exception as e:
        print(f"EdgeDB query error: {e}")
        # Return a server error if the database query fails
        return jsonify({"error": "Database query failed"}), 500

    if not message:
        # If no messages exist in the database, return a default/empty response
        # Returning a 204 No Content or a default JSON with an empty field is standard.
        return jsonify({"pixel_data_b64": ""}), 200

    # The data fetched from EdgeDB is a bytes object
    raw_bytes = message.payload

    # 2. Encode the raw bytes into a Base64 string
    # Python's base64.b64encode returns bytes, so we decode it to a UTF-8 string
    base64_string = base64.b64encode(raw_bytes).decode("utf-8")

    # 3. Wrap the Base64 string in a JSON object with the expected key
    response_data = {"pixel_data_b64": base64_string}

    # Use jsonify to correctly set the Content-Type to application/json
    return jsonify(response_data), 200
