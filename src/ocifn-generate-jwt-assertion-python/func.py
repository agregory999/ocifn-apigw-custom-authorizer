import io
import json
import logging
import time
import jwt

from fdk import response

# Constants
IDCS_AUDIENCE = 'https://identity.oraclecloud.com/'

# Function code for generating JWT User Assertions
def handler(ctx, data: io.BytesIO = None):

    # Main routine
    logging.getLogger().info("Enter JWT User Assertion Function")
    
    
    try:
        # Load Function Config
        cfg = dict(ctx.Config())

        # Establish Logging based on config (if there is one) - otherwise the default is INFO
        try:
            if cfg["DEBUG"] and cfg["DEBUG"] == "true":
                logging.getLogger().setLevel(logging.DEBUG)
                logging.getLogger().debug(f"DEBUG level set")
            else:
                logging.getLogger().debug(f"INFO level set")
                logging.getLogger().setLevel(logging.INFO)
        except:
            logging.getLogger().debug(f"INFO level set")
            logging.getLogger().setLevel(logging.INFO)

        # These are required - otherwise fail
        try:
            idcs_appid = cfg["IDCS_CLIENT_ID"]
            logging.getLogger().debug(f"IDCS Client ID: {idcs_appid}")
        except:
            raise

        # Check API Key - not required
        validKey = None
        try:
            validKey = cfg["VALID-API-KEY"]
            logging.getLogger().debug(f"Valid API Key: {validKey}")
        except:
            True

        # Body must exist
        if not data.getvalue():
            raise ValueError("Function requires JSON input")

        # Collect details from body
        body = json.loads(data.getvalue())
        username = body.get("username")
        expiry = body.get("seconds") if body.get("seconds") else 3600
        apiKey = body.get("api-key")

        if not validKey:
            # Not requiring API Key to be sent in
            logging.getLogger().debug(f"No valid API Key - therefore not required as incoming")
        else:
            logging.getLogger().debug(f"Valid API Key: {validKey}")
            if (validKey != apiKey):
                raise ValueError(f"Invalid API Key: {validKey}!={apiKey}")

        # Now generate an Assertion
        # Time
        epoch_time = int(time.time())
        exp_time = epoch_time + expiry
        logging.getLogger().debug('Current Time: ' + str(epoch_time) + ' : Expires: ' + str(exp_time))

        # Generate Token
        with open('server.key', 'rb') as f:
            key = f.read()

        # Payload with required fields
        payload = {'prn':username,'sub':username,'iss': idcs_appid, 'aud':IDCS_AUDIENCE, 'iat':epoch_time,'exp':exp_time}
        header = {'kid': 'agcert2'}

        # Conditionally add scope if provided
        if body.get("scopes"):
            payload["scopes"] = body.get("scopes")

        # Do the encoding
        assertion = jwt.encode(headers=header,payload=payload,key=key,algorithm="RS256")
        logging.getLogger().debug(f"Assertion: {assertion}")

        # Return
        return response.Response(
            ctx, response_data=json.dumps(
                {"assertion": assertion}),
            headers={"Content-Type": "application/json"}
        )
    # Generic Handler
    except (Exception, ValueError) as ex:
        logging.getLogger().error("Error: {0}".format(ex), exc_info=1)
        return response.Response(
            ctx, response_data=json.dumps(
            {"error": str(ex)}),
            headers={"Content-Type": "application/json"}
        )
