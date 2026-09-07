"""Approved Pedidos360 lab deployment; explicit stages and durable, non-secret journal.

Run in WSL. AWS_CLI may point to the Windows aws.exe authenticated by the operator.
Never retries an interrupted/failed write: inspect AWS and reconcile the journal first.
No deletion, shared-resource changes or credentials/profile configuration.
"""
import argparse
import base64
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-1"
ACCOUNT = "002996184293"
TAGS = {"Project": "Pedidos360", "Course": "DSY1107", "Environment": "lab"}
EVIDENCE = ROOT / "docs/evidence/phase5"
PRIVATE = Path.home() / ".config/pedidos360/aws"
CLI = os.environ.get("AWS_CLI") or shutil.which("aws")
JOURNAL = EVIDENCE / "deployment-journal.json"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def call(service, operation, payload=None):
    if not CLI:
        raise RuntimeError("Set AWS_CLI to the authenticated AWS CLI executable")
    command = [CLI, service, operation, "--region", REGION, "--output", "json", "--no-cli-pager"]
    path = None
    try:
        if payload:
            fd, filename = tempfile.mkstemp(prefix="request-", suffix=".json", dir=PRIVATE)
            path = Path(filename)
            with os.fdopen(fd, "w") as stream:
                json.dump(payload, stream)
            filename = subprocess.check_output(["wslpath", "-w", filename], text=True).strip() if CLI.endswith(".exe") else filename
            command += ["--cli-input-json", "file://" + filename]
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        if result.returncode:
            error = result.stderr.strip()
            for secret_file in PRIVATE.glob("*-password"):
                error = error.replace(secret_file.read_text().strip(), "[REDACTED]")
            raise RuntimeError(error)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    finally:
        if path:
            path.unlink(missing_ok=True)


def tags(name=None):
    return [{"Key": k, "Value": v} for k, v in {**TAGS, **({"Name": name} if name else {})}.items()]


def spec(kind, name):
    return [{"ResourceType": kind, "Tags": tags(name)}]


def write(key, service, operation, payload, sensitive=()):
    if key in state["steps"]:
        old = state["steps"][key]
        if old["status"] != "complete":
            raise RuntimeError(f"Inspect interrupted/failed step {key}; automatic retry prohibited")
        print(f"verified journal: {key}", flush=True)
        return old["response"]
    step = {"startedAt": now(), "service": service, "operation": operation,
            "request": {k: ("[REDACTED]" if k in sensitive else v) for k, v in payload.items()}, "status": "in-progress"}
    state["steps"][key] = step
    save(JOURNAL, state)
    try:
        response = call(service, operation, payload)
        step.update(status="complete", completedAt=now(), response=response)
        save(JOURNAL, state)
        print(f"completed: {key}", flush=True)
        return response
    except Exception as error:
        step.update(status="failed-review-required", error=str(error), completedAt=now())
        save(JOURNAL, state)
        raise


def response(key):
    step = state["steps"][key]
    if step["status"] != "complete":
        raise RuntimeError(f"Incomplete dependency: {key}")
    return step["response"]


def network():
    vpc = write("vpc", "ec2", "create-vpc", {"CidrBlock": "10.36.0.0/16", "TagSpecifications": spec("vpc", "pedidos360-vpc")})["Vpc"]["VpcId"]
    for attr in ("EnableDnsSupport", "EnableDnsHostnames"):
        write(attr, "ec2", "modify-vpc-attribute", {"VpcId": vpc, attr: {"Value": True}})
    for name, cidr, az in (("public-b", "10.36.0.0/24", "us-east-1b"), ("private-b", "10.36.10.0/24", "us-east-1b"), ("private-c", "10.36.20.0/24", "us-east-1c")):
        write(name, "ec2", "create-subnet", {"VpcId": vpc, "CidrBlock": cidr, "AvailabilityZone": az, "TagSpecifications": spec("subnet", "pedidos360-" + name)})
    igw = write("igw", "ec2", "create-internet-gateway", {"TagSpecifications": spec("internet-gateway", "pedidos360-igw")})["InternetGateway"]["InternetGatewayId"]
    write("attach-igw", "ec2", "attach-internet-gateway", {"VpcId": vpc, "InternetGatewayId": igw})
    for kind in ("public", "private"):
        rt = write(kind + "-rt", "ec2", "create-route-table", {"VpcId": vpc, "TagSpecifications": spec("route-table", "pedidos360-" + kind + "-rt")})["RouteTable"]["RouteTableId"]
        if kind == "public":
            write("internet-route", "ec2", "create-route", {"RouteTableId": rt, "DestinationCidrBlock": "0.0.0.0/0", "GatewayId": igw})
        for name in (["public-b"] if kind == "public" else ["private-b", "private-c"]):
            write("associate-" + name, "ec2", "associate-route-table", {"RouteTableId": rt, "SubnetId": response(name)["Subnet"]["SubnetId"]})
    for name in ("vpclink", "alb", "app", "db"):
        sg = write(name + "-sg", "ec2", "create-security-group", {"VpcId": vpc, "GroupName": "pedidos360-" + name + "-sg", "Description": "Pedidos360 " + name + " dedicated security boundary", "TagSpecifications": spec("security-group", "pedidos360-" + name + "-sg")})["GroupId"]
        write(name + "-remove-default-egress", "ec2", "revoke-security-group-egress", {"GroupId": sg, "IpPermissions": [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]})
    for source, target, port in (("vpclink", "alb", 80), ("alb", "app", 8180), ("app", "db", 3306)):
        for direction, group, peer in (("egress", source, target), ("ingress", target, source)):
            write(f"{source}-{target}-{direction}", "ec2", "authorize-security-group-" + direction, {"GroupId": response(group + "-sg")["GroupId"], "IpPermissions": [{"IpProtocol": "tcp", "FromPort": port, "ToPort": port, "UserIdGroupPairs": [{"GroupId": response(peer + "-sg")["GroupId"]}]}]})
    write("app-https-egress", "ec2", "authorize-security-group-egress", {"GroupId": response("app-sg")["GroupId"], "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS Entra SSM and packages"}]}]})


def database():
    subnets = [response(name)["Subnet"]["SubnetId"] for name in ("private-b", "private-c")]
    write("db-subnets", "rds", "create-db-subnet-group", {"DBSubnetGroupName": "pedidos360-db-subnets", "DBSubnetGroupDescription": "Pedidos360 private database subnets", "SubnetIds": subnets, "Tags": tags()})
    write("db-parameters", "rds", "create-db-parameter-group", {"DBParameterGroupName": "pedidos360-mysql84", "DBParameterGroupFamily": "mysql8.4", "Description": "Pedidos360 MySQL 8.4 mandatory TLS", "Tags": tags()})
    write("db-require-tls", "rds", "modify-db-parameter-group", {"DBParameterGroupName": "pedidos360-mysql84", "Parameters": [{"ParameterName": "require_secure_transport", "ParameterValue": "1", "ApplyMethod": "immediate"}]})
    for name in ("master", "catalog-app", "catalog-migration", "orders-app", "orders-migration"):
        path = PRIVATE / (name + "-password")
        if not path.exists():
            if "rds" in state["steps"]:
                raise RuntimeError("Recorded RDS exists but its local secret file is missing; do not generate replacement credentials")
            path.write_text(secrets.token_hex(16 if name == "master" else 24) + "\n")
            path.chmod(0o600)
    master_password = (PRIVATE / "master-password").read_text().strip()
    if not 8 <= len(master_password) <= 41:
        raise RuntimeError("RDS MySQL master password must contain 8 to 41 characters")
    write("rds", "rds", "create-db-instance", {
        "DBInstanceIdentifier": "pedidos360-mysql", "DBInstanceClass": "db.t3.micro", "Engine": "mysql", "EngineVersion": "8.4.11",
        "AllocatedStorage": 20, "StorageType": "gp3", "StorageEncrypted": True,
        "MasterUsername": "pedidos360_master", "MasterUserPassword": master_password,
        "DBSubnetGroupName": "pedidos360-db-subnets", "DBParameterGroupName": "pedidos360-mysql84",
        "VpcSecurityGroupIds": [response("db-sg")["GroupId"]], "AvailabilityZone": "us-east-1b", "Port": 3306,
        "MultiAZ": False, "PubliclyAccessible": False, "BackupRetentionPeriod": 1, "DeletionProtection": True,
        "AutoMinorVersionUpgrade": False, "EnablePerformanceInsights": False, "CopyTagsToSnapshot": True,
        "Tags": tags("pedidos360-mysql")}, sensitive=("MasterUserPassword",))


def compute():
    key = PRIVATE / "pedidos360-deploy"
    if not key.exists():
        if "ssh-key" in state["steps"]:
            raise RuntimeError("Recorded SSH key exists but the local private key is missing; use SSM or recover the key")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "pedidos360-deploy", "-f", str(key)], check=True)
    write("ssh-key", "ec2", "import-key-pair", {"KeyName": "pedidos360-deploy", "PublicKeyMaterial": base64.b64encode(key.with_suffix(".pub").read_bytes()).decode(), "TagSpecifications": spec("key-pair", "pedidos360-deploy")})
    # Observe the current operator egress, never an invented or broad CIDR.
    if "temporary-ssh" not in state["steps"]:
        with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=20) as stream:
            address = ipaddress.IPv4Address(stream.read().decode().strip())
        if not address.is_global:
            raise RuntimeError("SSH operator address is not a public IPv4")
        write("temporary-ssh", "ec2", "authorize-security-group-ingress", {"GroupId": response("app-sg")["GroupId"], "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": str(address) + "/32", "Description": "Pedidos360 temporary operator deployment"}]}]})
    bootstrap = (ROOT / "deploy/ec2-bootstrap.sh").read_bytes()
    write("ec2", "ec2", "run-instances", {
        "ImageId": "ami-025d99823a4caad37", "InstanceType": "t3.medium", "MinCount": 1, "MaxCount": 1,
        "ClientToken": "pedidos360-002996184293-20260906-app-v1", "KeyName": "pedidos360-deploy",
        "NetworkInterfaces": [{"DeviceIndex": 0, "SubnetId": response("public-b")["Subnet"]["SubnetId"], "Groups": [response("app-sg")["GroupId"]], "AssociatePublicIpAddress": True, "DeleteOnTermination": True}],
        "IamInstanceProfile": {"Arn": f"arn:aws:iam::{ACCOUNT}:instance-profile/LabInstanceProfile"},
        "MetadataOptions": {"HttpTokens": "required", "HttpEndpoint": "enabled", "HttpPutResponseHopLimit": 1},
        "CreditSpecification": {"CpuCredits": "standard"},
        "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 20, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}],
        "TagSpecifications": spec("instance", "pedidos360-app") + spec("volume", "pedidos360-app-root"),
        "UserData": base64.b64encode(bootstrap).decode()})


def gateway():
    vpc = response("vpc")["Vpc"]["VpcId"]
    subnets = [response(name)["Subnet"]["SubnetId"] for name in ("private-b", "private-c")]
    alb = write("alb", "elbv2", "create-load-balancer", {"Name": "pedidos360-internal-alb", "Subnets": subnets, "SecurityGroups": [response("alb-sg")["GroupId"]], "Scheme": "internal", "Type": "application", "IpAddressType": "ipv4", "Tags": tags()})["LoadBalancers"][0]["LoadBalancerArn"]
    tg = write("target-group", "elbv2", "create-target-group", {"Name": "pedidos360-bff-tg", "Protocol": "HTTP", "Port": 8180, "VpcId": vpc, "TargetType": "instance", "HealthCheckProtocol": "HTTP", "HealthCheckPath": "/actuator/health", "HealthCheckIntervalSeconds": 30, "HealthCheckTimeoutSeconds": 5, "HealthyThresholdCount": 2, "UnhealthyThresholdCount": 3, "Matcher": {"HttpCode": "200"}, "Tags": tags()})["TargetGroups"][0]["TargetGroupArn"]
    write("register-bff", "elbv2", "register-targets", {"TargetGroupArn": tg, "Targets": [{"Id": response("ec2")["Instances"][0]["InstanceId"], "Port": 8180}]})
    listener = write("listener", "elbv2", "create-listener", {"LoadBalancerArn": alb, "Protocol": "HTTP", "Port": 80, "DefaultActions": [{"Type": "forward", "TargetGroupArn": tg}], "Tags": tags()})["Listeners"][0]["ListenerArn"]
    link = write("vpclink", "apigatewayv2", "create-vpc-link", {"Name": "pedidos360-vpclink", "SubnetIds": subnets, "SecurityGroupIds": [response("vpclink-sg")["GroupId"]], "Tags": TAGS})["VpcLinkId"]
    api = write("http-api", "apigatewayv2", "create-api", {"Name": "pedidos360-http-api", "ProtocolType": "HTTP", "Description": "Pedidos360 BFF with Microsoft Entra JWT", "CorsConfiguration": {"AllowOrigins": ["http://localhost:5173", "http://127.0.0.1:5173"], "AllowMethods": ["GET", "POST", "OPTIONS"], "AllowHeaders": ["Authorization", "Content-Type"], "ExposeHeaders": ["Location"], "AllowCredentials": False, "MaxAge": 300}, "Tags": TAGS})["ApiId"]
    entra = json.loads((ROOT / "config/entra-public.json").read_text())
    assert entra["scopes"] == ["Catalog.Read", "Orders.Read", "Orders.Create"]
    authorizer = write("jwt-authorizer", "apigatewayv2", "create-authorizer", {"ApiId": api, "Name": "pedidos360-entra-jwt", "AuthorizerType": "JWT", "IdentitySource": ["$request.header.Authorization"], "JwtConfiguration": {"Issuer": f"https://login.microsoftonline.com/{entra['tenantId']}/v2.0", "Audience": [entra["apiClientId"]]}})["AuthorizerId"]
    integration = write("integration", "apigatewayv2", "create-integration", {"ApiId": api, "IntegrationType": "HTTP_PROXY", "IntegrationMethod": "ANY", "IntegrationUri": listener, "ConnectionType": "VPC_LINK", "ConnectionId": link, "PayloadFormatVersion": "1.0", "TimeoutInMillis": 30000, "RequestParameters": {"overwrite:path": "$request.path"}})["IntegrationId"]
    routes = [
        ("GET /api/v1/productos", ["Catalog.Read"]),
        ("GET /api/v1/productos/{id}", ["Catalog.Read"]),
        ("GET /api/v1/pedidos", ["Orders.Read"]),
        ("GET /api/v1/pedidos/{id}", ["Orders.Read"]),
        ("POST /api/v1/pedidos", ["Orders.Create"]),
        ("GET /api/v1/me", entra["scopes"]),
        ("GET /api/v1/admin/pedidos", ["Orders.Read"]),
    ]
    for index, (route, scopes) in enumerate(routes):
        write("route-" + str(index), "apigatewayv2", "create-route", {"ApiId": api, "RouteKey": route, "AuthorizationType": "JWT", "AuthorizerId": authorizer, "AuthorizationScopes": scopes, "Target": "integrations/" + integration})
    log_name = "/pedidos360/api-gateway"
    write("api-logs", "logs", "create-log-group", {"logGroupName": log_name, "tags": TAGS})
    write("api-logs-retention", "logs", "put-retention-policy", {"logGroupName": log_name, "retentionInDays": 7})
    write("default-stage", "apigatewayv2", "create-stage", {"ApiId": api, "StageName": "$default", "AutoDeploy": True, "DefaultRouteSettings": {"ThrottlingRateLimit": 5.0, "ThrottlingBurstLimit": 10}, "AccessLogSettings": {"DestinationArn": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{log_name}", "Format": '{"requestId":"$context.requestId","routeKey":"$context.routeKey","status":"$context.status","latency":"$context.responseLatency"}'}, "Tags": TAGS})
    save(ROOT / "config/aws-public.json", {"account": ACCOUNT, "region": REGION, "apiId": api, "apiEndpoint": response("http-api")["ApiEndpoint"], "apiBaseUrl": response("http-api")["ApiEndpoint"] + "/api/v1"})


def status():
    result = {"at": now()}
    if "ec2" in state["steps"] and state["steps"]["ec2"]["status"] == "complete":
        instance = response("ec2")["Instances"][0]["InstanceId"]
        result["ec2"] = call("ec2", "describe-instances", {"InstanceIds": [instance]})
        result["ssm"] = call("ssm", "describe-instance-information", {"Filters": [{"Key": "InstanceIds", "Values": [instance]}]})
        item = result["ec2"]["Reservations"][0]["Instances"][0]
        print(f"EC2 {instance}: {item['State']['Name']}, public IP {item.get('PublicIpAddress')}")
        print("SSM: " + json.dumps([{"id": x["InstanceId"], "status": x["PingStatus"]} for x in result["ssm"]["InstanceInformationList"]]))
    if "rds" in state["steps"] and state["steps"]["rds"]["status"] == "complete":
        result["rds"] = call("rds", "describe-db-instances", {"DBInstanceIdentifier": "pedidos360-mysql"})
        print("RDS: " + result["rds"]["DBInstances"][0]["DBInstanceStatus"])
    if "target-group" in state["steps"] and state["steps"]["target-group"]["status"] == "complete":
        result["targets"] = call("elbv2", "describe-target-health", {"TargetGroupArn": response("target-group")["TargetGroups"][0]["TargetGroupArn"]})
        print("Target health: " + json.dumps(result["targets"]["TargetHealthDescriptions"]))
    if "vpclink" in state["steps"] and state["steps"]["vpclink"]["status"] == "complete":
        result["vpclink"] = call("apigatewayv2", "get-vpc-link", {"VpcLinkId": response("vpclink")["VpcLinkId"]})
        print("VPC Link: " + result["vpclink"]["VpcLinkStatus"])
    save(EVIDENCE / "status-latest.json", result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["preflight", "network", "database", "compute", "gateway", "status"])
    args = parser.parse_args()
    os.umask(0o077)
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    global state
    state = json.loads(JOURNAL.read_text()) if JOURNAL.exists() else {"account": ACCOUNT, "region": REGION, "approval": "User approved FASE 4 checkpoint and FASE 5 on 2026-09-06", "steps": {}}
    if state["account"] != ACCOUNT or state["region"] != REGION:
        raise RuntimeError("Journal target mismatch")
    identity = call("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT or not identity["Arn"].startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/voclabs/"):
        raise RuntimeError("AWS account/role mismatch")
    save(EVIDENCE / "identity-latest.json", {"at": now(), **identity})
    print("Identity verified: " + identity["Arn"], flush=True)
    if args.stage == "preflight":
        results = {
            "vpcs": call("ec2", "describe-vpcs", {"Filters": [{"Name": "tag:Project", "Values": ["Pedidos360"]}]}),
            "keys": call("ec2", "describe-key-pairs"),
            "rdsParameters": call("rds", "describe-db-parameter-groups"),
            "rdsSubnets": call("rds", "describe-db-subnet-groups"),
            "vpcLinks": call("apigatewayv2", "get-vpc-links"),
            "logs": call("logs", "describe-log-groups", {"logGroupNamePrefix": "/pedidos360/"}),
        }
        save(EVIDENCE / "preflight-names.json", {"at": now(), "results": results})
        print(json.dumps(results, indent=2))
    elif args.stage == "network":
        network()
    elif args.stage == "database":
        database()
    elif args.stage == "compute":
        compute()
    elif args.stage == "gateway":
        gateway()
    elif args.stage == "status":
        status()


if __name__ == "__main__":
    main()
