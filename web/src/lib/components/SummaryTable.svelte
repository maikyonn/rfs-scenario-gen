<script lang="ts">
	import type { ExperimentSummary } from '$lib/types';

	let { summary, methods }: {
		summary: ExperimentSummary;
		methods: string[];
	} = $props();

	function fmtPct(rate: number, total: number): string {
		const pct = Math.round(rate * 100);
		const count = Math.round(rate * total);
		return `${pct}% (${count}/${total})`;
	}

	function fmtTime(seconds: number): string {
		return `${seconds.toFixed(1)}s`;
	}

	function fmtDuration(ms: number): string {
		const s = ms / 1000;
		return `${s.toFixed(1)}s`;
	}

	function fmtRating(rating: number): string {
		const filled = Math.round(rating);
		const stars = '\u2605'.repeat(filled) + '\u2606'.repeat(5 - filled);
		return `${rating.toFixed(1)} ${stars}`;
	}

	type MetricRow = {
		label: string;
		getValue: (method: string) => string;
	};

	const metricRows: MetricRow[] = [
		{
			label: 'Collision rate',
			getValue: (m) => {
				const s = summary[m];
				return s ? fmtPct(s.collision_rate, s.total) : '--';
			}
		},
		{
			label: 'Avg collision time',
			getValue: (m) => {
				const s = summary[m];
				return s && s.avg_collision_time > 0 ? fmtTime(s.avg_collision_time) : '--';
			}
		},
		{
			label: 'Avg generation time',
			getValue: (m) => {
				const s = summary[m];
				return s && s.avg_duration_ms > 0 ? fmtDuration(s.avg_duration_ms) : '--';
			}
		},
		{
			label: 'Avg rating',
			getValue: (m) => {
				const s = summary[m];
				return s && s.avg_rating > 0 ? fmtRating(s.avg_rating) : '--';
			}
		},
		{
			label: 'Failure rate',
			getValue: (m) => {
				const s = summary[m];
				return s ? fmtPct(s.fail_rate, s.total) : '--';
			}
		}
	];
</script>

<div class="table-wrap">
	<table>
		<thead>
			<tr>
				<th class="metric-col">Metric</th>
				{#each methods as method}
					<th class="method-col">{method}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each metricRows as row}
				<tr>
					<td class="metric-label">{row.label}</td>
					{#each methods as method}
						<td class="metric-value">{row.getValue(method)}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.table-wrap {
		overflow-x: auto;
		border-radius: 8px;
		border: 1px solid var(--color-border);
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	th {
		text-align: left;
		padding: 10px 14px;
		font-weight: 600;
		font-size: 0.78rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-muted);
		background: rgba(96, 165, 250, 0.06);
		border-bottom: 1px solid var(--color-border);
	}

	td {
		padding: 10px 14px;
		border-bottom: 1px solid var(--color-border);
	}

	tr:last-child td {
		border-bottom: none;
	}

	.metric-label {
		color: var(--color-muted);
		font-weight: 500;
	}

	.metric-value {
		color: var(--color-text);
		font-variant-numeric: tabular-nums;
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.82rem;
	}

	.method-col {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.75rem;
	}

	tr:nth-child(even) td {
		background: rgba(255, 255, 255, 0.02);
	}
</style>
