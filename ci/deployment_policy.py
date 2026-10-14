"""Pure deployment eligibility; no Git, filesystem, credential or network access."""
BASE = '$CI_COMMIT_BRANCH == "main" && $CI_COMMIT_REF_PROTECTED == "true"'
SOURCES = '($CI_PIPELINE_SOURCE == "push" || $CI_PIPELINE_SOURCE == "web")'
PACKAGE_RULE = f"{BASE} && {SOURCES}"
RULES = {
    "production_preflight": f'{BASE} && $CI_PIPELINE_SOURCE == "web" && $JARVIS_OPERATION == "preflight"',
    "bootstrap_production": f'{BASE} && $CI_PIPELINE_SOURCE == "web" && $JARVIS_OPERATION == "bootstrap"',
    "deploy_production": f'{BASE} && {SOURCES} && $JARVIS_OPERATION == "deploy"',
}


def require_production_context(environment, action):
    if action not in {"preflight", "bootstrap", "deploy", "acceptance"}:
        raise RuntimeError("Unknown production action")
    if (environment.get("CI_COMMIT_BRANCH") != "main"
            or environment.get("CI_COMMIT_REF_PROTECTED") != "true"
            or environment.get("CI_ENVIRONMENT_NAME") != "production"
            or environment.get("CI_PIPELINE_SOURCE") not in {"push", "web"}
            or environment.get("JARVIS_OPERATION", "deploy") != ("deploy" if action == "acceptance" else action)):
        raise RuntimeError("Production operations require the protected-main production job context")
    if action in {"preflight", "bootstrap"} and environment.get("CI_PIPELINE_SOURCE") != "web":
        raise RuntimeError("Preflight/bootstrap require separately approved web pipelines")