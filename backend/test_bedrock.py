import boto3, json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

body = json.dumps({
    "messages": [
        {
            "role": "user",
            "content": [{"text": "Say: WAREHOUSEIQ READY"}]
        }
    ],
    "inferenceConfig": {
        "maxTokens": 50,
        "temperature": 0.1
    }
})

resp = client.invoke_model(
    modelId="amazon.nova-lite-v1:0",
    body=body,
    contentType="application/json",
    accept="application/json"
)

result = json.loads(resp["body"].read())
print(result["output"]["message"]["content"][0]["text"])