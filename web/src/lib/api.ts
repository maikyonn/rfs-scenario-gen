import type {
	Dataset,
	DatasetRecord,
	DatasetStats,
	Experiment,
	ExperimentDetail,
	ExperimentResult,
	ExperimentSummary
} from './types';

const BASE = '';

async function get<T>(path: string): Promise<T> {
	const res = await fetch(`${BASE}${path}`);
	if (!res.ok) throw new Error(`GET ${path}: ${res.status} ${res.statusText}`);
	return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
	if (!res.ok) throw new Error(`POST ${path}: ${res.status} ${res.statusText}`);
	return res.json();
}

// ── Datasets ────────────────────────────────────────────────────────────────

export function fetchDatasets(): Promise<Dataset[]> {
	return get('/api/datasets');
}

export function fetchRecords(
	datasetId: number,
	opts: { page?: number; per_page?: number; crash_type?: string; search?: string } = {}
): Promise<{ records: DatasetRecord[]; total: number; page: number; per_page: number }> {
	const params = new URLSearchParams();
	if (opts.page) params.set('page', String(opts.page));
	if (opts.per_page) params.set('per_page', String(opts.per_page));
	if (opts.crash_type) params.set('crash_type', opts.crash_type);
	if (opts.search) params.set('search', opts.search);
	const qs = params.toString();
	return get(`/api/datasets/${datasetId}/records${qs ? '?' + qs : ''}`);
}

export function fetchDatasetStats(datasetId: number): Promise<DatasetStats> {
	return get(`/api/datasets/${datasetId}/stats`);
}

// ── Experiments ─────────────────────────────────────────────────────────────

export function fetchExperiments(): Promise<Experiment[]> {
	return get('/api/experiments');
}

export function fetchExperiment(id: number): Promise<ExperimentDetail> {
	return get(`/api/experiments/${id}`);
}

export function fetchExperimentResults(
	id: number,
	opts: { page?: number; per_page?: number } = {}
): Promise<{ results: ExperimentResult[]; total: number; page: number; per_page: number }> {
	const params = new URLSearchParams();
	if (opts.page) params.set('page', String(opts.page));
	if (opts.per_page) params.set('per_page', String(opts.per_page));
	const qs = params.toString();
	return get(`/api/experiments/${id}/results${qs ? '?' + qs : ''}`);
}

export function fetchExperimentSummary(id: number): Promise<ExperimentSummary> {
	return get(`/api/experiments/${id}/summary`);
}

export function createExperiment(body: {
	name: string;
	dataset_id: number;
	methods: string[];
	crash_type_filter?: string;
	max_records?: number;
}): Promise<{ id: number; total_jobs: number; status: string }> {
	return post('/api/experiments', body);
}

// ── Ratings ─────────────────────────────────────────────────────────────────

export function submitRating(body: {
	generation_id: string;
	rating: number;
	feedback_text?: string;
}): Promise<{ id: number }> {
	return post('/api/ratings', body);
}
