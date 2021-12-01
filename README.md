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

Diagram of the sequence involved:

![Sequence Diagram](images/AssertionintoToken-Extended-APIGWwithCustomAuthorizerFunction.jpg)

## Initial Setup

(Work in Progress)

[Create a self-signed cert/key combination](https://major.io/2007/08/02/generate-self-signed-certificate-and-key-in-one-line/)
[Generate a public key](https://stackoverflow.com/questions/5244129/use-rsa-private-key-to-generate-public-key)
[Create an OCI Vault](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Concepts/keyoverview.htm)
Place private and public key in OCI vault
[Set up Functions Application and FN command line](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartguidestop.htm) 

## Deployment of Functions

(Work in Progress)

1) Clone this repo
2) Deploy functions to function app

Deployment can happen from a cloud shell or local shell.  from the repo root (and assuming your Functions App is called *FunctionsApp*):
```bash
cd src
fn -v deploy  --app FunctionsApp ocifn-jwt-assertion-python
fn -v deploy  --app FunctionsApp ocifn-apigw-assertion-authorizer-python
```

3) After deployment, use the OCI Console to copy the function OCID fo the *ocifn-apigw-assertion-authorizer-python* function.  Use that for the next section.

## Security Post-Deployment

In order for a function to have access to tenancy resources, it must be given permission via Dynamic Group.  The way this works is by defining a Dynamic Group, where the function itself is a member.  This means that code executing inside the function assumes the group identity of the Dynamic Group.

![Dynamic Group](images/DynamicGroup.png)

To give permissions for the Dynamic Group to "do something", a policy is written.  This policy can be tenancy-wide, or within a compartment.  The policy follows the standard syntax of *Allow <group or dynamic group> to <verb> <resource> in <compartment or tenancy> where <optional extras>*.

An example policy shown here allows the *AGFunctionsGroup* to perform the tasks highlighted.  One of these is to invoke another function, which is required here.  The more generic one (all resources) covers anything in a compartment, which includes access to Vault.  We could scope this down way further so that onyl a specific secret could be read.

![Policy](images/DGPolicy.png)

### Function Configs (after deployment)

Each function needs to be configured with runtime configs prior to running.  These can be viewed as "Constants", but can be changed at runtime if necessary.

#### ocifn-generate-jwt-assertion-python:

```
fn config f FunctionsApp ocifn-generate-jwt-assertion-python IDCS_CLIENT_ID 7ed17eb8d2604c67a26fb3a5d565702c
```
Optionally, the following could be set.  If the VALID-API-KEY is set, the incoming call requires it to be passed in order for a match to occur.  This effectively adds simple auth to the function, as the API KEY can be a UUID or un-guessable string.
```
fn config f FunctionsApp ocifn-generate-jwt-assertion-python DEBUG true
fn config f FunctionsApp ocifn-generate-jwt-assertion-python VALID-API-KEY 12345
```
#### ocifn-apigw-assertion-authorizer-python:
Here the function is configured with required parameters that it uses to access IDCS.  These could be changed based on the underlying implementation of Oauth.  Note that the ones that are OCIDs are there to prevent "hard-coded" sensitive data.  These OCIDs are references to Vault Secrets, so the actual values must be placed into a Vault and the OCIDs copied.
```
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_APIGW_SCOPE https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443/apigw
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_CLIENT_ID 7ed17eb8d2604c67a26fb3a5d565702c
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_ISSUER https://identity.oraclecloud.com/
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python IDCS_CLIENT_SECRET_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayatktorrcwbzynippxloxuhycj5ubmntpjwif7t5tcydqa
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python ASSERTER_PUBLIC_KEY_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayaxd2mozeuq4vhontb3u4xlwa7ifghca6dsltksiuew5xq
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python ASSERTER_PRIVATE_KEY_OCID ocid1.vaultsecret.oc1.iad.amaaaaaaytsgwayai22l6jfmkmsdwcqducpb45n47maayofyknfzknd44w4q
```
Optionally set DEBUG to see more details in the Logs.  
```
fn config f FunctionsApp ocifn-apigw-assertion-authorizer-python DEBUG true
```

## Invoking the JWT Assertion Generator

This function can be invoked via command line as follows.  Each response contains a JWT User Assertion, verifiable using [JWT Debugger](https://jwt.io):

With API GW Scope  (and no API Key)
```
echo '{"username":"andrew.gregory@oracle.com","seconds":3600,"scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python
```
The response will be:
```
{"assertion": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6ImFnY2VydDIifQ.eyJwcm4iOiJhbmRyZXcuZ3JlZ29yeUBvcmFjbGUuY29tIiwic3ViIjoiYW5kcmV3LmdyZWdvcnlAb3JhY2xlLmNvbSIsImlzcyI6IjdlZDE3ZWI4ZDI2MDRjNjdhMjZmYjNhNWQ1NjU3MDJjIiwiYXVkIjoiaHR0cHM6Ly9pZGVudGl0eS5vcmFjbGVjbG91ZC5jb20vIiwiaWF0IjoxNjM4Mzg5ODU1LCJleHAiOjE2MzgzOTM0NTUsInNjb3BlcyI6WyJodHRwczovL2l1anltMmpzd21pZTM1ZXdid3VhNG96eDN5LmFwaWdhdGV3YXkudXMtYXNoYnVybi0xLm9jaS5jdXN0b21lci1vY2kuY29tL2FwaWd3Il19.F-mvC4MuEB7QsHmpUAkNs9Y7q13MzVKPtvsK0wASAtjtzYFSNs257AOpvP-YId_0KdzmJepBupG2ZZXZ_AOePg41K8wKAIbE8i1nzGccYKBcAFj1F_aCpyFVkTBo9pWhcTr-HrcGcKTXNuB3Ykgln0LxC7OiNCBMUH3d4nUobw4uO3CElpdRNsw6TX7E1HNf9CuCFfKIBxELI9E16VBXxTHFJ55WflgE3YSOavIfh-vldpEuAY6mf_J5SK3GBXshyz0cnCANM9Ny9_Q5trQFXwgWAslATQyI15oWveznoXAdf68-wT8NBnogIdpY1jlskjdPRu7KRIKkdlXjxz5eng"}
```

With Multiple Scopes (and API Key if required):
echo '{"username":"andrew.gregory@oracle.com","seconds":1800,"api-key":"12345","scopes":["https://iujym2jswmie35ewbwua4ozx3y.apigateway.us-ashburn-1.oci.customer-oci.com/apigw","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443urn:opc:resource:consumer::all","https://486492DB75A64F4CB3F2C5FCFA5384B8.integration.ocp.oraclecloud.com:443/ic/api/"]}'|fn invoke FunctionsApp ocifn-generate-jwt-assertion-python
```
The response will be:
```
{"assertion": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6ImFnY2VydDIifQ.eyJwcm4iOiJhbmRyZXcuZ3JlZ29yeUBvcmFjbGUuY29tIiwic3ViIjoiYW5kcmV3LmdyZWdvcnlAb3JhY2xlLmNvbSIsImlzcyI6IjdlZDE3ZWI4ZDI2MDRjNjdhMjZmYjNhNWQ1NjU3MDJjIiwiYXVkIjoiaHR0cHM6Ly9pZGVudGl0eS5vcmFjbGVjbG91ZC5jb20vIiwiaWF0IjoxNjM4Mzg5ODAwLCJleHAiOjE2MzgzOTE2MDAsInNjb3BlcyI6WyJodHRwczovL2l1anltMmpzd21pZTM1ZXdid3VhNG96eDN5LmFwaWdhdGV3YXkudXMtYXNoYnVybi0xLm9jaS5jdXN0b21lci1vY2kuY29tL2FwaWd3IiwiaHR0cHM6Ly80ODY0OTJEQjc1QTY0RjRDQjNGMkM1RkNGQTUzODRCOC5pbnRlZ3JhdGlvbi5vY3Aub3JhY2xlY2xvdWQuY29tOjQ0M3VybjpvcGM6cmVzb3VyY2U6Y29uc3VtZXI6OmFsbCIsImh0dHBzOi8vNDg2NDkyREI3NUE2NEY0Q0IzRjJDNUZDRkE1Mzg0QjguaW50ZWdyYXRpb24ub2NwLm9yYWNsZWNsb3VkLmNvbTo0NDMvaWMvYXBpLyJdfQ.rsY0mH0AJrdfI327kAiPYseJ33XEIqvObxMidRAyQHIkhBXt6_0hZdVmtuTwjX3eFa176QBQ1rHwhIa4nAjFQYfAoSPqFa2FP0eZ_sorybfilOqW4gCrMQ2KFneCGRrpMpLxrCVghQ1_0fmDNP3FwRX-co_pv3SvcdQuGhAJzZ94G73AdfIcldDchXKpir8onHomhMQ4q5Do8QZn1lr8hIRaFDMP3QzH4xfVwUlu8stmSWJKwprqjnj4Yzmv_tDq70CNiG8EIjfeaC6BmvFrQnqYcFIdpI-_bvCM7uNFFQ44nwIbVRhL2Cquhp9f7FBZd3soA7eA_LNVNyodgcwlQA"}
```

Note: The function can be invoked with no scopes, and it will produce an assertion.  However, this is not useful for the API Gateway (this example).  

## Logging

Logs from the functions go to the OCI Functions Invoke Log.  Within a minute of running either function, the logs can be seen