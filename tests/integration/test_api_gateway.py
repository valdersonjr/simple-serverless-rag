import os

import boto3
import pytest
import requests

"""
Make sure env variable AWS_SAM_STACK_NAME exists with the name of the stack we are going to test. 
"""


class TestApiGateway:

    @pytest.fixture()
    def ingest_url(self):
        """Get the Ingest endpoint URL from CloudFormation Stack outputs."""
        stack_name = os.environ.get("AWS_SAM_STACK_NAME")

        if stack_name is None:
            raise ValueError('Please set the AWS_SAM_STACK_NAME environment variable to the name of your stack')

        client = boto3.client("cloudformation")

        try:
            response = client.describe_stacks(StackName=stack_name)
        except Exception as e:
            raise Exception(
                f"Cannot find stack {stack_name} \n" f'Please make sure a stack with the name "{stack_name}" exists'
            ) from e

        stacks = response["Stacks"]
        stack_outputs = stacks[0]["Outputs"]
        api_outputs = [output for output in stack_outputs if output["OutputKey"] == "IngestApiUrl"]

        if not api_outputs:
            raise KeyError(f"IngestApiUrl not found in stack {stack_name}")

        return api_outputs[0]["OutputValue"]  # Extract url from stack outputs

    def test_api_gateway(self, ingest_url):
        """Call the API Gateway ingest endpoint and check that it enqueues."""
        response = requests.post(
            ingest_url,
            json={"doc_id": "test-doc", "text": "hello", "chunk_size": 5, "persist": False},
            timeout=20,
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "enqueued"
        assert body["doc_id"] == "test-doc"
