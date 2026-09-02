// Optional sync helper. Call only after an explicit user action and only for a
// job id already created by that user. It performs exactly one status read.
export async function refreshKnownJob(getStatus, jobId, onUpdate) {
  if (!jobId) return {state: 'missing_job', reads: 0};
  try {
    const state = await getStatus(jobId);
    onUpdate(state);
    return {state: state.status || 'unknown', reads: 1};
  } catch (error) {
    return {state: 'refresh_failed', reads: 1, error};
  }
}
