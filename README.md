# OCI Functions for Custom Authoization

Set of functions and associated artifacts in support of allowing OCI API Gateway to authorize clients based on JWT User Assertion.

The following functions exist:

- ocifn-generate-jwt-assertion-python
- ocifn-apigw-assertion-authorizer-python

The *oci-apigw-assertion-authorizer-python* function is used as an API Gateway Authorizer function.  This is documented here:
[API Gateway Authorizer](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingauthorizerfunction.htm)

Rather than looking at an ACCESS TOKEN, it is expecting a JWT USER ASSERTION instead.  The assertion can be constructed outside of the scope of this project, or can be created by calling the *ocifn-generate-jwt-assertion-python* function with appropriate parameters (see below).   Once the Assertion is constructed with the correct scopes, it is to be sent as a standard HTTP Header called *Assertion*.  The API Gateway Deployment will pick off this header and send the assertion base64-encoded string into the function. 

## Function Logic

The Authorizer is designed to process scopes, as sent inside the Assertion.  The scopes are in the form of a list, which could look like this:

```
echo '{"username":"andrew.gregory@oracle.com","seconds":60,"api-key":"12345","scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python
```
or (with multiple scopes)
```
echo '{"username":"andrew.gregory@oracle.com","seconds":1800,"api-key":"12345","scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443urn:opc:resource:consumer::all","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443/ic/api/"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python
```
1) The function first looks for the scope containing the API GW itself - this scope allows the function to hit an Oauth2.0 token endpoint (Oracle IDCS) and receive a valid access token which it verifies.  The presence of the requested scope in the access token is taken to mean that the caller was allowed to invoke API GW.

2a) Following this step, the API GW scope is removed from the list of scopes in order to facilitate further processing.  If there are no remaining scopes in the list, this means that the API GW is simply calling an unprotected backend service, likely internal to the OCI tenancy.  The function in this case returns a positive response that the Authorizer was successful.

2b) If there are remaining scopes (ie those for OIC) are used to create a new User Assertion internally, using a function->function call to *ocifn-generate-jwt-assertion-python*.  This new assertion is then sent again to the Oauth token endpoint in exchange for a valid access token containing the requested scopes.  If this call is successful, the resulting access token is validated and returned as an "Authorizer Context" - see the docs.

Upon return to API GW, each route within the deploiyment that requires an Authorization header with a valid access token is configured with API GW request processing logic that 
a) removes the Assertion header (not needed for downstream call)
b) adds the Bearer access token it got back to the Authorization header
c) validates the required scope needed to call the downstream service - this must be returned from the function.

In cases where authentication or authorization fails, API GW returns a 401 error to the client.


## Deployment

(Work in Progress)

### Function Configs (after deployment)

ocifn-generate-jwt-assertion-python:

```
fn config f FunctionsApp ocifn-generate-jwt-assertion-python IDCS_CLIENT_ID 7ed17eb8d2604c67a26fb3a5d565702c
```
(optional)
```
fn config f FunctionsApp ocifn-generate-jwt-assertion-python DEBUG true
fn config f FunctionsApp ocifn-generate-jwt-assertion-python VALID-API-KEY 12345
```
ocifn-apigw-assertion-authorizer-python:
```
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_APIGW_SCOPE https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443/apigw
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_CLIENT_ID 7ed17eb8d2604c67a26fb3a5d565702c
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_ISSUER https://identity.oraclecloud.com/\t
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_CLIENT_SECRET_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayatktorrcwbzynippxloxuhycj5ubmntpjwif7t5tcydqa
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python ASSERTER_PUBLIC_KEY_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayaxd2mozeuq4vhontb3u4xlwa7ifghca6dsltksiuew5xq
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python ASSERTER_PRIVATE_KEY_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayai22l6jfmkmsdwcqducpb45n47maayofyknfzknd44w4q
```
(optional)
```
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python DEBUG true
```
## Invoking

With 1 Scope
echo '{"username":"andrew.gregory@oracle.com","seconds":60,"api-key":"12345","scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python

Multiple Scopes:
echo '{"username":"andrew.gregory@oracle.com","seconds":1800,"api-key":"12345","scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443urn:opc:resource:consumer::all","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443/ic/api/"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python {"assertion": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6ImFnY2VydDIifQ.eyJwcm4iOiJhbmRyZXcuZ3JlZ29yeUBvcmFjbGUuY29tIiwic3ViIjoiYW5kcmV3LmdyZWdvcnlAb3JhY2xlLmNvbSIsImlzcyI6IjdlZDE3ZWI4ZDI2MDRjNjdhMjZmYjNhNWQ1NjU3MDJjIiwiYXVkIjoiaHR0cHM6Ly9pZGVudGl0eS5vcmFjbGVjbG91ZC5jb20vIiwiaWF0IjoxNjM4MzczMDI1LCJleHAiOjE2MzgzNzQ4MjUsInNjb3BlcyI6WyJodHRwczovL2l1anltMmpzd21pZTM1ZXdid3VhNG96eDN5LmFwaWdhdGV3YXkudXMtYXNoYnVybi0xLm9jaS5jdXN0b21lci1vY2kuY29tL2FwaWd3IiwiaHR0cHM6Ly80ODY0OTJEQjc1QTY0RjRDQjNGMkM1RkNGQTUzODRCOC5pbnRlZ3JhdGlvbi5vY3Aub3JhY2xlY2xvdWQuY29tOjQ0M3VybjpvcGM6cmVzb3VyY2U6Y29uc3VtZXI6OmFsbCIsImh0dHBzOi8vNDg2NDkyREI3NUE2NEY0Q0IzRjJDNUZDRkE1Mzg0QjguaW50ZWdyYXRpb24ub2NwLm9yYWNsZWNsb3VkLmNvbTo0NDMvaWMvYXBpLyJdfQ.j_Seyb0ejrZ3PYlu2RuNIrCjaDVMCyutXYYfigs5aQ8CXIEVMcuiHmMbVw454rhgH6camkMKaHO6G8OQ05ZSrNiKAjtbttYWbvc5U48y68jlGvbXc6VWKArel7cVfCbAUI1M_RUowt-VvNAwJ9XUp4VBcLozlDUOox6gfTJQWLiLSz4vUn-cp0MPmVfFOkiivYbeVBVLsc_e4Og8X4Lx9oRDxJ1FRcI_BPAocjz_o-q7t69rnM5A0tTxkqJ8Fzo2W7mqK-jFtERV2uIpsNngxkhMavT-UFipO4im_i7W3E7__-3K26hfxAqt_K7JLNWmBnleFw8RThbqPvrpZ3L4Fw"}

No Scope (should error)