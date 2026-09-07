param([ValidateSet('us-east-1', 'us-west-2')][string]$Region = 'us-east-1')

# Phase 4 inventory only. No create/update/delete, user data, credentials or secret-value APIs.
$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot "../docs/evidence/phase4/inventory/$Region"
New-Item -ItemType Directory -Force -Path $destination | Out-Null

function Read-AwsInventory([string]$Name, [string[]]$CliArgs, [string]$Query) {
    $errorPath = Join-Path $destination "$Name.stderr.txt"
    $commandArgs = @($CliArgs) + @('--region', $Region, '--query', $Query, '--output', 'json', '--no-cli-pager')
    $startedAt = [DateTime]::UtcNow.ToString('o')
    $result = & aws @commandArgs 2> $errorPath
    $exitCode = $LASTEXITCODE
    $errorText = if (Test-Path -LiteralPath $errorPath) { Get-Content -Raw -LiteralPath $errorPath } else { '' }
    $response = if ($exitCode -eq 0) { ($result -join "`n") | ConvertFrom-Json -NoEnumerate } else { $null }
    [ordered]@{ at=$startedAt; command=(@('aws') + $commandArgs); exitCode=$exitCode; response=$response; error=$errorText } |
        ConvertTo-Json -Depth 70 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $destination "$Name.json")
    $count = if ($exitCode -eq 0) { @($response).Count } else { 'UNKNOWN' }
    Write-Output "$Region $Name exit=$exitCode entries=$count"
}

Read-AwsInventory 'vpcs' @('ec2','describe-vpcs') 'Vpcs[].{Id:VpcId,Default:IsDefault,Cidr:CidrBlock,State:State,Tags:Tags}'
Read-AwsInventory 'subnets' @('ec2','describe-subnets') 'Subnets[].{Id:SubnetId,Vpc:VpcId,AZ:AvailabilityZone,Cidr:CidrBlock,Default:DefaultForAz,PublicIp:MapPublicIpOnLaunch,Available:AvailableIpAddressCount,Tags:Tags}'
Read-AwsInventory 'route-tables' @('ec2','describe-route-tables') 'RouteTables[].{Id:RouteTableId,Vpc:VpcId,Routes:Routes,Associations:Associations,Tags:Tags}'
Read-AwsInventory 'security-groups' @('ec2','describe-security-groups') 'SecurityGroups[].{Id:GroupId,Vpc:VpcId,Name:GroupName,Description:Description,Ingress:IpPermissions,Egress:IpPermissionsEgress,Tags:Tags}'
Read-AwsInventory 'internet-gateways' @('ec2','describe-internet-gateways') 'InternetGateways[].{Id:InternetGatewayId,Attachments:Attachments,Tags:Tags}'
Read-AwsInventory 'nat-gateways' @('ec2','describe-nat-gateways') 'NatGateways[].{Id:NatGatewayId,Vpc:VpcId,Subnet:SubnetId,State:State,Tags:Tags}'
Read-AwsInventory 'vpc-endpoints' @('ec2','describe-vpc-endpoints') 'VpcEndpoints[].{Id:VpcEndpointId,Vpc:VpcId,Type:VpcEndpointType,Service:ServiceName,State:State,Tags:Tags}'
Read-AwsInventory 'instances' @('ec2','describe-instances') 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,Image:ImageId,Vpc:VpcId,Subnet:SubnetId,PrivateIp:PrivateIpAddress,PublicIp:PublicIpAddress,Profile:IamInstanceProfile.Arn,Key:KeyName,Tags:Tags}'
Read-AwsInventory 'volumes' @('ec2','describe-volumes') 'Volumes[].{Id:VolumeId,Size:Size,Type:VolumeType,State:State,Encrypted:Encrypted,Attachments:Attachments,Tags:Tags}'
Read-AwsInventory 'addresses' @('ec2','describe-addresses') 'Addresses[].{Allocation:AllocationId,PublicIp:PublicIp,Association:AssociationId,Instance:InstanceId,Tags:Tags}'
Read-AwsInventory 'key-pairs' @('ec2','describe-key-pairs') 'KeyPairs[].{Id:KeyPairId,Name:KeyName,Type:KeyType,Tags:Tags}'
Read-AwsInventory 'rds-instances' @('rds','describe-db-instances') 'DBInstances[].{Id:DBInstanceIdentifier,Arn:DBInstanceArn,Engine:Engine,Version:EngineVersion,Class:DBInstanceClass,Status:DBInstanceStatus,Public:PubliclyAccessible,Encrypted:StorageEncrypted,MultiAZ:MultiAZ,SubnetGroup:DBSubnetGroup,Groups:VpcSecurityGroups,Tags:TagList}'
Read-AwsInventory 'rds-clusters' @('rds','describe-db-clusters') 'DBClusters[].{Id:DBClusterIdentifier,Arn:DBClusterArn,Engine:Engine,Status:Status,Tags:TagList}'
Read-AwsInventory 'rds-subnet-groups' @('rds','describe-db-subnet-groups') 'DBSubnetGroups[].{Name:DBSubnetGroupName,Vpc:VpcId,Status:SubnetGroupStatus,Subnets:Subnets}'
Read-AwsInventory 'rds-snapshots' @('rds','describe-db-snapshots','--snapshot-type','manual') 'DBSnapshots[].{Id:DBSnapshotIdentifier,DB:DBInstanceIdentifier,Engine:Engine,Status:Status,Tags:TagList}'
Read-AwsInventory 'http-apis' @('apigatewayv2','get-apis') 'Items[].{Id:ApiId,Name:Name,Protocol:ProtocolType,Endpoint:ApiEndpoint,Tags:Tags}'
Read-AwsInventory 'vpc-links-v2' @('apigatewayv2','get-vpc-links') 'Items[].{Id:VpcLinkId,Name:Name,Status:VpcLinkStatus,Subnets:SubnetIds,Groups:SecurityGroupIds,Tags:Tags}'
Read-AwsInventory 'rest-apis' @('apigateway','get-rest-apis') 'items[].{Id:id,Name:name,Endpoint:endpointConfiguration,Tags:tags}'
Read-AwsInventory 'load-balancers' @('elbv2','describe-load-balancers') 'LoadBalancers[].{Name:LoadBalancerName,Arn:LoadBalancerArn,Type:Type,Scheme:Scheme,Vpc:VpcId,State:State,AZs:AvailabilityZones}'
Read-AwsInventory 'target-groups' @('elbv2','describe-target-groups') 'TargetGroups[].{Name:TargetGroupName,Arn:TargetGroupArn,Protocol:Protocol,Port:Port,Vpc:VpcId,TargetType:TargetType}'
Read-AwsInventory 'cloudmap-namespaces' @('servicediscovery','list-namespaces') 'Namespaces[].{Id:Id,Name:Name,Arn:Arn,Type:Type}'
Read-AwsInventory 'cloudmap-services' @('servicediscovery','list-services') 'Services[].{Id:Id,Name:Name,Arn:Arn,Instances:InstanceCount}'
Read-AwsInventory 'stacks' @('cloudformation','describe-stacks') 'Stacks[].{Name:StackName,Id:StackId,Status:StackStatus,Created:CreationTime,Tags:Tags}'
Read-AwsInventory 'managed-instances' @('ssm','describe-instance-information') 'InstanceInformationList[].{Id:InstanceId,Status:PingStatus,Platform:PlatformName,Version:PlatformVersion}'
Read-AwsInventory 'tagged-resources' @('resourcegroupstaggingapi','get-resources') 'ResourceTagMappingList'
