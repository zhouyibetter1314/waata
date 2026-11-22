import type { CreateRunRequest } from '../../api';

export type RunFormErrors = Partial<
  Record<
    'target_url' | 'goal' | 'expected_behavior' | 'max_steps_per_case',
    string
  >
>;

export function validateRunRequest(value: CreateRunRequest): RunFormErrors {
  const errors: RunFormErrors = {};
  try {
    const url = new URL(value.target_url);
    if (!['http:', 'https:'].includes(url.protocol)) {
      errors.target_url = '目标地址必须使用 HTTP 或 HTTPS';
    } else if (url.username || url.password) {
      errors.target_url = '目标地址不能包含用户名或密码';
    }
  } catch {
    errors.target_url = '请输入有效的绝对 HTTP(S) 地址';
  }
  if (!value.goal.trim()) errors.goal = '请输入自然语言测试目标';
  if (!value.expected_behavior.trim())
    errors.expected_behavior = '请输入预期行为';
  const maxSteps = value.options?.max_steps_per_case;
  if (
    maxSteps !== undefined &&
    (!Number.isInteger(maxSteps) || maxSteps <= 0)
  ) {
    errors.max_steps_per_case = '每个用例的最大步骤数必须是正整数';
  }
  return errors;
}
