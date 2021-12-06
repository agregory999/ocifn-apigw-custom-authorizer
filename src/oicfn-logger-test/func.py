import io
import json
import logging
import oci
import uuid

from fdk import response
from datetime import datetime

def handler(ctx, data: io.BytesIO = None):
    signer = oci.auth.signers.get_resource_principals_signer()
    try:
        logging.getLogger('oci').info("Inside Python Logging function")
        loggingingestion_client = oci.loggingingestion.LoggingClient({}, signer=signer)
        body = json.loads(data.getvalue())
        message = body.get("message")
        
        put_logs_response = loggingingestion_client.put_logs(
            log_id="ocid1.log.oc1.iad.amaaaaaaytsgwayavve2rpbqjrjzdvv3kt3rbq5ds4wxmoakcygd6tues2zq",
            put_logs_details=oci.loggingingestion.models.PutLogsDetails(
                specversion="1.0",
                log_entry_batches=[
                    oci.loggingingestion.models.LogEntryBatch(
                        entries=[
                            oci.loggingingestion.models.LogEntry(
                                data=str(message),
                                id=str(uuid.uuid1()),
                                time=datetime.strptime(
                                "2021-12-03T17:00:10.178Z",
                                "%Y-%m-%dT%H:%M:%S.%fZ")
                            )
                        ],
                        source="MyFunction",
                        type="LoggingMessage",
                        subject="SomeSubject",
                        defaultlogentrytime=datetime.strptime(
                            "2038-04-28T02:40:07.255Z", "%Y-%m-%dT%H:%M:%S.%fZ")
                    )
                ]
            ),
            timestamp_opc_agent_processing=datetime.strptime(
                "2036-10-10T11:12:19.676Z",
                "%Y-%m-%dT%H:%M:%S.%fZ")    
        )    
        return response.Response(
            ctx, response_data=json.dumps(
                {"message": "Logged Message"}),
            headers={"Content-Type": "application/json"}
        )

    except Exception as ex:
        m = str(ex)
        return response.Response(
            ctx, response_data=json.dumps(
                {"error": f"Hello {m}"}),
            headers={"Content-Type": "application/json"}
        )
