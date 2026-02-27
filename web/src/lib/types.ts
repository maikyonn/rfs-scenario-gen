export interface Dataset {
	id: number;
	name: string;
	source: string | null;
	record_count: number;
	created_at: string;
}

export interface DatasetStats {
	total: number;
	by_crash_type: Record<string, number>;
	by_pattern: Record<string, number>;
}

export interface GenerationSummary {
	id: string;
	status: string;
	collision_detected: boolean | null;
	collision_time: number | null;
	mp4_url: string | null;
	thumbnail_url: string | null;
	avg_rating: number | null;
	duration_ms: number | null;
	config_json: string | null;
	error: string | null;
}

export interface DatasetRecord {
	id: number;
	dataset_id: number;
	text_desc: string;
	crash_type: string;
	pattern: string;
	metadata_json: string | null;
	generations: Record<string, GenerationSummary | null>;
}

export interface Experiment {
	id: number;
	name: string;
	dataset_id: number;
	status: string;
	methods: string[];
	methods_json: string;
	record_ids: number[] | null;
	record_ids_json: string | null;
	created_at: string;
}

export interface ExperimentProgress {
	[method: string]: {
		completed: number;
		failed: number;
		pending: number;
	};
}

export interface ExperimentDetail extends Experiment {
	total: number;
	progress: ExperimentProgress;
}

export interface ExperimentResult {
	record: {
		id: number;
		text_desc: string;
		crash_type: string;
		pattern: string;
	};
	generations: Record<string, GenerationSummary | null>;
}

export interface MethodSummary {
	total: number;
	collision_rate: number;
	avg_collision_time: number;
	avg_rating: number;
	avg_duration_ms: number;
	fail_rate: number;
}

export type ExperimentSummary = Record<string, MethodSummary>;
