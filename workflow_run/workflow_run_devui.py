import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from agent_framework.devui import serve

from opsagent.workflows.triage_workflow import create_triage_workflow
from opsagent.workflows.dynamic_workflow import create_dynamic_workflow


def main():
    """Main entry point for the Ops Agents DevUI."""
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Creating Dynamic Workflow...")

    # Create the dynamic workflow with all specialized agents
    workflow = create_dynamic_workflow()

    logger.info("Starting DevUI server...")
    logger.info("Available at: http://localhost:8100")
    logger.info("Workflow: dynamic-workflow")

    import os
    os.environ['ENABLE_OTEL'] = 'true'

    # Launch DevUI with the workflow
    serve(
        entities=[workflow],
        port=8100,
        auto_open=True,
    )


if __name__ == "__main__":
    main()
