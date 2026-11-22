"""The optional export exposes run metadata and keeps request data local."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from waata.observability import LangfuseObserver, Observation


class LangfuseObserverTests(IsolatedAsyncioTestCase):
    async def test_exports_safe_children_and_final_status(self):
        client = Mock()
        client.create_trace_id.return_value = "trace-id"
        root = client.start_observation.return_value
        root.trace_id = "trace-id"
        observer = LangfuseObserver(client=client, model_name="test-model")
        run = await observer.start_run("run-id")
        await run.record(
            Observation(
                "model.completed",
                "run-id",
                "case-id",
                "step-id",
                {"phase": "runner", "total_tokens": 42, "prompt": "private"},
            )
        )
        await run.record(
            Observation("run.finished", "run-id", fields={"status": "succeeded"})
        )

        root.start_observation.assert_called_once_with(
            name="waata.model",
            as_type="generation",
            model="test-model",
            metadata={
                "run_id": "run-id",
                "case_id": "case-id",
                "step_id": "step-id",
                "phase": "runner",
                "total_tokens": 42,
            },
            level="DEFAULT",
            usage_details={"total": 42},
        )
        root.start_observation.return_value.end.assert_called_once()
        root.update.assert_called_once_with(
            metadata={"run_id": "run-id", "status": "succeeded"}, level="DEFAULT"
        )
        self.assertEqual(await run.close(), "trace-id")
        root.end.assert_called_once()
        client.flush.assert_not_called()
