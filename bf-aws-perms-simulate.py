import argparse
import boto3
import json
import requests

from termcolor import colored
from tqdm import tqdm
from typing import Dict, List, Optional


def get_aws_permissions() -> Dict[str, List[str]]:
    """
    Download all the AWS permissions per service from the AWS Policy Generator.
    
    Returns:
        permissions (Dict[str, List[str]]): A dictionary containing service names as keys and action lists as values.
    """
    url = "https://awspolicygen.s3.amazonaws.com/js/policies.js"
    response = requests.get(url)

    if response.status_code != 200:
        print(colored("Error: Unable to fetch AWS policies.", "red"))
        return {}

    resp_text = response.text.replace("app.PolicyEditorConfig=", "")
    policies = json.loads(resp_text)
    permissions = {}

    for service in policies["serviceMap"]:
        service_name = policies["serviceMap"][service]["StringPrefix"]
        actions = [action for action in policies["serviceMap"][service]["Actions"]]
        permissions[service_name] = actions

    return permissions


def check_user_permissions(
    permissions: Dict[str, List[str]],
    iam_client: boto3.client,
    user_arn: str,
    batch_size: int = 50
) -> List[str]:
    """
    Check all the permissions of a user using simulate_principal_policy.
    
    Args:
        permissions (Dict[str, List[str]]): A dictionary containing service names as keys and action lists as values.
        iam_client (boto3.client): IAM client object from boto3.
        user_arn (str): The ARN of the user to check permissions for.
        batch_size (int, optional): The size of the action batches to simulate. Defaults to 50.

    Returns:
        user_permissions (List[str]): A list of allowed permissions for the user.
    """
    action_batches = [f"{service}:{action}" for service, actions in permissions.items() for action in actions]
    user_permissions = []

    print(colored(f"Checking {len(action_batches)} permissions for {user_arn}...", "cyan"))

    for i in tqdm(range(0, len(action_batches), batch_size)):
        perms = action_batches[i:i + batch_size]
        response = iam_client.simulate_principal_policy(PolicySourceArn=user_arn, ActionNames=perms)

        for result in response["EvaluationResults"]:
            allowed = result["EvalDecision"] == "allowed"
            action = result["EvalActionName"]

            if allowed:
                user_permissions.append(action)

    return user_permissions


def main(aws_profile: str, user_arn: Optional[str] = "") -> None:
    """
    Main function to check user permissions.

    Args:
        aws_profile (str): AWS profile name to use.
        user_arn (Optional[str], optional): User ARN to check permissions for. Defaults to an empty string.
    """
    boto_session = boto3.Session(profile_name=aws_profile)
    iam_client = boto_session.client("iam")

    if not user_arn:
        sts_client = boto_session.client("sts")
        user = sts_client.get_caller_identity()
        user_arn = user["Arn"]

    if not user_arn:
        print(colored("Error: Unable to get user ARN, please specify it.", "red"))
        return

    aws_permissions = get_aws_permissions()

    if not aws_permissions:
        print(colored("Error: Unable to get AWS permissions.", "red"))
        return
    
    user_permissions = check_user_permissions(aws_permissions, iam_client, user_arn)
    user_permissions = sorted(user_permissions)

    # Print user permissions nicely
    print(colored("User Permissions:", "green"))
    for permission in user_permissions:
        print(colored(f"  - {permission}", "yellow"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Asks AWS permissions for a user using simulatePrincipalPolicy")
    parser.add_argument("--profile", type=str, required=True, help="AWS profile name to use")
    parser.add_argument("--arn", type=str, required=False, help="User/Role ARN to check permissions for (by defaults uses current user)")

    args = parser.parse_args()
    main(aws_profile=args.profile, user_arn=args.arn)

