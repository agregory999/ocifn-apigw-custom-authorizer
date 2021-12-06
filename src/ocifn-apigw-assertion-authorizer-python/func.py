import io
import json
import logging
import IdcsClient
import oci
import base64
import jwt

from datetime import datetime
from fdk import response
from jwt import PyJWKClient

# Constants
APIGW_SCOPE = "/apigw"
APIGW_AUDIENCE = "https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com"
REMOTE_JWKS_URL = "https://idcs-4c88472bb4c2475aa6ddcfabc52af290.identity.oraclecloud.com/admin/v1/SigningCert/jwk"
JWT_FUNC_OCID = "ocid1.fnfunc.oc1.iad.aaaaaaaakkqbgddsph6twwqhli77qyuz7tbgapmwumw27ingfsggzdwc5dzq"
JWT_FUNC_ENDPOINT = "https://whdbzdmju4a.us-ashburn-1.functions.oci.oraclecloud.com"

def handler(ctx, data: io.BytesIO = None):
    
    # Load Function Config 
    cfg = dict(ctx.Config())

    # Establish Logging based on config (if there is one) - otherwise the default is INFO
    try:
        if cfg["DEBUG"] and cfg["DEBUG"].lower() == "true":
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger('authorizer').debug(f"DEBUG level set")
        else:
            logging.getLogger().setLevel(logging.INFO)
            logging.getLogger('authorizer').debug(f"INFO level set")
    except:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger('authorizer').debug(f"INFO level set")

    # Main Function routine
    try:
        logging.getLogger('authorizer').info("Entering Python authorizer function: {0}".format(data.getvalue()))

### Properties Setup  #### 

        body = json.loads(data.getvalue())
        tok = body.get("token")

        # Load Function Config
        cfg = dict(ctx.Config())
        idcs_client_id = cfg["IDCS_CLIENT_ID"]
        idcs_client_secret_ocid = cfg["IDCS_CLIENT_SECRET_OCID"]
        idcs_token_issuer = cfg["IDCS_ISSUER"]
        # idcs_apigw_scope = cfg["IDCS_APIGW_SCOPE"]
        # asserter_private_key_ocid = cfg["ASSERTER_PRIVATE_KEY_OCID"]
        asserter_public_key_ocid = cfg["ASSERTER_PUBLIC_KEY_OCID"]

        # Grab secret values from OCI Vault
        idcs_client_secret = get_text_secret(idcs_client_secret_ocid)
        asserter_public_key = get_text_secret(asserter_public_key_ocid)
        logging.getLogger('authorizer').debug("IDCS Secret (dec): " + idcs_client_secret)
        logging.getLogger('authorizer').debug("Asserter PubKey (dec): " + asserter_public_key)

### OAUTH IDCS Setup ###

        # Base IDCS Options from file
        options = getOptions()
        
        # Set additional fields based on configurables
        options["ClientId"] = idcs_client_id
        options["ClientSecret"] = idcs_client_secret
        options["TokenIssuer"] = idcs_token_issuer
        logging.getLogger('authorizer').debug("IDCS Options: " + str(options))

        # Obtain IDCS Client
        am = IdcsClient.AuthenticationManager(options)
        logging.getLogger('authorizer').debug("Auth Manager: " + str(am))

### Assertion Decode w/o verify (need scope) #### 

        # Decode Assertion 
        assertion = jwt.decode(jwt=tok,key=asserter_public_key,audience=idcs_token_issuer,algorithms=["RS256"])
        
        # Gracefully handle the potential of no scopes being sent in.
        scopes = assertion["scopes"] if "scopes" in assertion else []

        if len(scopes) == 0:
            # Nothing requested, so I don't know what to do
            raise ValueError("At least 1 scope must be passed in")

        # Validate against API GW Scope first
        if (APIGW_AUDIENCE + APIGW_SCOPE) in scopes:
            # Check against API GW
            # Set up call to IDCS with single scope for APIGW
            # If Token issued and contains scope, then we are ok to proceed
            # Otherwise return error
            # IDCS Call to token endpoint using UserAssertion
            access_token_result = am.userAssertion(user_assertion=tok,scope=APIGW_AUDIENCE+APIGW_SCOPE)
            access_token = access_token_result.getAccessToken()
            logging.getLogger('authorizer').debug("Access Token: " + str(access_token))

            # For token verification, we want to use the remote JWKS to verify
            remote_jwks_key = getRemoteJWKS(access_token,REMOTE_JWKS_URL)
            logging.getLogger('authorizer').debug("Remote Key: " + str(remote_jwks_key))

            # Decode the token with full verification, just to prove it is good
            access_token_decoded = jwt.decode(
                access_token,
                remote_jwks_key,
                audience=APIGW_AUDIENCE,
                options={"verify_signature": True},
                algorithms=["RS256"]
            )
            logging.getLogger('authorizer').debug("Access Token1: " + str(access_token))
            logging.getLogger('authorizer').info("Access Token1 Decoded: {0}".format(access_token_decoded))

            # Lastly, remove the scope from the list
            scopes.remove(APIGW_AUDIENCE+APIGW_SCOPE)

        # Now, if no remaining scopes, then the backend has no protection
        if len(scopes) == 0:
            # Simply return something to satisfy API GW
            # Get Correct expiration
            expires_at_epoch = access_token_decoded["exp"]
            issued_at_epoch = access_token_decoded["iat"]
            expires_at_iso = datetime.fromtimestamp(expires_at_epoch).isoformat()

            # Build valid response
            resp = {}
            resp["active"] = "true"
            resp["principal"] = assertion["prn"]
            resp["scope"] = str(access_token_decoded["scope"]).split(" ")
            resp["expiresAt"] = str(expires_at_iso)

            # Return Successful
            logging.getLogger('authorizer').info(f'Authorizer Returning Success: {resp["principal"]} Scope: {resp["scope"]}')
            return response.Response(
                ctx, response_data=json.dumps(resp),
                headers={"Content-Type": "application/json"}
            )

        # Last case - still scopes to deal with - these should be given with new access token
        else: 
            # List of scopes will be assigned to new token request
            # At this time, create another UserAssertion via Function call.  Re-use scopes from previous assertion for now
            username = assertion["prn"]

            # Hard code for now
            downstream_scopes = []
            func_resp = createUserAssertion(JWT_FUNC_OCID, JWT_FUNC_ENDPOINT, username, downstream_scopes)
            logging.getLogger('authorizer').debug("Function Response: " + func_resp)

            # Get assertion from JSON
            json_resp = json.loads(func_resp)
            downstream_assertion = json_resp["assertion"]

            # Call OAuth again
            # Scopes was a List [] but for IDCS it is a space-separated string
            idcs_scopes = " ".join(scopes)
            access_token2_result = am.userAssertion(user_assertion=downstream_assertion,scope=idcs_scopes)
            access_token2 = access_token2_result.getAccessToken()

            # For token verification, we want to use the remote JWKS to verify
            remote_jwks_key = getRemoteJWKS(access_token2,REMOTE_JWKS_URL)
            logging.getLogger('authorizer').debug("Remote Key: " + str(remote_jwks_key))

            # Decode the token with full verification, just to prove it is good
            access_token_decoded2 = jwt.decode(
                access_token2,
                remote_jwks_key,
                audience="https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443",
                options={"verify_signature": True},
                algorithms=["RS256"]
            )

            logging.getLogger('authorizer').debug("Access Token2: " + str(access_token2))
            logging.getLogger('authorizer').debug("Access Token Decoded2: {0}".format(access_token_decoded2))

            # Get Correct expiration
            expires_at_epoch = access_token_decoded2["exp"]
            issued_at_epoch = access_token_decoded2["iat"]
            expires_at_iso = datetime.fromtimestamp(expires_at_epoch).isoformat()

            # Build valid response
            resp = {}
            resp["active"] = True
            resp["principal"] = assertion["prn"]
            resp["scope"] = str(access_token_decoded2["scope"]).split(" ")
            resp["expiresAt"] = str(expires_at_iso)

            # Additional context for API GW to use (header manipulation)
            context = {}
            context["access_token"] = access_token2
            resp["context"] = context
            
            # Return Successful
            logging.getLogger('authorizer').info("Returning Access Token to API GW")
            return response.Response(
                ctx, response_data=json.dumps(resp),
                headers={"Content-Type": "application/json"}
            )
    # Default Error Handler - return nothing good
    except (Exception, ValueError) as ex:

        logging.getLogger('authorizer').error(f"Error: {ex}",exc_info=0)
        return response.Response(
            ctx, response_data=json.dumps(
                {"active": False, "wwwAuthenticate": "Bearer realm=\"identity.oraclecloud.com\""}),
            headers={"Content-Type": "application/json"},
            status_code=500
        )
    
########## Helper functions ##########

# Grab secret text from OCI Vault
def get_text_secret(secret_ocid):
    #decrypted_secret_content = ""
    signer = oci.auth.signers.get_resource_principals_signer()
    try:
        client = oci.secrets.SecretsClient({}, signer=signer)
        secret_content = client.get_secret_bundle(secret_ocid).data.secret_bundle_content.content.encode('utf-8')
        decrypted_secret_content = base64.b64decode(secret_content).decode("utf-8")
        #print(f"Secret content: {decrypted_secret_content}", flush=True)

    except Exception as ex:
        logging.getLogger('oci-secret').error(f"Error obtaining secret: {str(ex)}")
        raise
    return decrypted_secret_content

# Load the configurations from the config.json file
def getOptions():
    fo = open("config.json", "r")
    config = fo.read()
    options = json.loads(config)
    return options

# Obtain Remote JWKS
def getRemoteJWKS(access_token,remote_jwks_url):
    jwks_client = PyJWKClient(remote_jwks_url)
    signing_key = jwks_client.get_signing_key_from_jwt(access_token)
    return signing_key.key

# Invoke Assertion Builder Function
def createUserAssertion(function_ocid, function_endpoint, username, scopes):
    # Access to OCI Functions via Resource Principal
    signer = oci.auth.signers.get_resource_principals_signer()
    functions_client = oci.functions.FunctionsInvokeClient({}, signer=signer, service_endpoint=function_endpoint)

    # Create Body with empty JSON
    request = {}
    request["username"] = username
    request["seconds"] = 1800
   #request["api-key"] = "12345"
    request["scopes"] = scopes

    # Base64 encode the request
    # Need to Stringify, then encode as bytes
    json_str = json.dumps(request)
    logging.getLogger('jwt-assertion').debug("Request to Function: " + json_str)

    function_response = functions_client.invoke_function(
        function_id=function_ocid,
        invoke_function_body=json_str
    )

    # Response is JSON?
    logging.getLogger('jwt-assertion').debug("Response from Function: " + str(function_response.data.text))
    return function_response.data.text
