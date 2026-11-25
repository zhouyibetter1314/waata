import createRequestJson from '../../../../contracts/http/examples/4gaboards-create-run.json' with { type: 'json' };
import reportJson from '../../../../contracts/http/examples/4gaboards-report.json' with { type: 'json' };
import runCreatedJson from '../../../../contracts/http/examples/4gaboards-run-created.json' with { type: 'json' };
import runDetailJson from '../../../../contracts/http/examples/4gaboards-run-detail.json' with { type: 'json' };
import type {
  CreateRunRequest,
  CreateRunResponse,
  RunDetail,
  RunReport,
  RunSummary,
} from '../../src/api';

export const createRunFixture = createRequestJson as CreateRunRequest;
export const runCreatedFixture = runCreatedJson as CreateRunResponse;
export const runDetailFixture = runDetailJson as RunDetail;
export const runReportFixture = reportJson as RunReport;

export function toRunSummary(detail: RunDetail): RunSummary {
  const {
    run_id,
    target_url,
    goal,
    status,
    verdict,
    created_at,
    started_at,
    finished_at,
  } = detail;
  return {
    run_id,
    target_url,
    goal,
    status,
    verdict,
    created_at,
    started_at,
    finished_at,
  };
}

export function cloneFixture<T>(value: T): T {
  return structuredClone(value);
}
