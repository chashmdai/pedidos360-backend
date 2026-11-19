"""Run a reviewed local script on the reconciled Pedidos360 EC2 through SSM Run Command.
Shared by scripts/ep4-ssm.py (evidence) and scripts/p360.py (operations console)."""
import base64
import json
from pathlib import Path
import time
import aws_deploy as aws


def instance_id():
    state = json.loads(aws.JOURNAL.read_text())
    return state["steps"]["ec2"]["response"]["Instances"][0]["InstanceId"]


def verify_target():
    """Lab identity of the target account and a running, project-tagged instance; returns the instance id."""
    identity = aws.call("sts", "get-caller-identity")
    assert identity["Account"] == aws.ACCOUNT and "/voclabs/" in identity["Arn"], "AWS account/role mismatch"
    instance = instance_id()
    actual = aws.call("ec2", "describe-instances", {"InstanceIds": [instance]})["Reservations"][0]["Instances"][0]
    assert actual["State"]["Name"] == "running" and {"Key": "Project", "Value": "Pedidos360"} in actual["Tags"], \
        "The project instance is not running"
    return instance


def run(script, arguments=(), instance=None, execution_timeout=1800, on_sent=None, poll=3):
    """Send the script (base64, exec'd by python3 as root) and wait for it; returns (command_id, invocation)."""
    instance = instance or instance_id()
    script = Path(script)
    encoded = base64.b64encode(script.read_bytes()).decode()
    argv = base64.b64encode(json.dumps([str(script), *arguments]).encode()).decode()
    command = ("python3 -c \"import base64,sys,json; sys.argv=json.loads(base64.b64decode('" + argv + "')); "
               "exec(compile(base64.b64decode('" + encoded + "'),'<pedidos360-ep4>','exec'))\"")
    result = aws.call("ssm", "send-command", {"InstanceIds": [instance], "DocumentName": "AWS-RunShellScript",
                                              "Comment": "Pedidos360 explicit project script", "TimeoutSeconds": 600,
                                              "Parameters": {"commands": [command], "executionTimeout": [str(execution_timeout)]}})
    command_id = result["Command"]["CommandId"]
    if on_sent:
        on_sent(command_id)
    while True:
        time.sleep(poll)
        try:
            invocation = aws.call("ssm", "get-command-invocation", {"CommandId": command_id, "InstanceId": instance})
        except RuntimeError as exc:
            if "InvocationDoesNotExist" in str(exc):
                continue
            raise
        if invocation["Status"] not in ("Pending", "InProgress", "Delayed"):
            return command_id, invocation
