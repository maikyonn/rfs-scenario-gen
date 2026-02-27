<script lang="ts">
	import type { Experiment, ExperimentProgress } from '$lib/types';

	let { experiment, progress }: {
		experiment: Experiment;
		progress: ExperimentProgress | null;
	} = $props();

	const statusColor = $derived(
		experiment.status === 'running' ? 'var(--color-accent)'
		: experiment.status === 'complete' ? '#4ade80'
		: 'var(--color-muted)'
	);

	const statusLabel = $derived(
		experiment.status === 'running' ? 'Running'
		: experiment.status === 'complete' ? 'Complete'
		: 'Pending'
	);

	const totalRecords = $derived(
		experiment.record_ids ? experiment.record_ids.length : null
	);

	function methodProgress(method: string): string {
		if (!progress || !progress[method]) return '--';
		const p = progress[method];
		const total = p.completed + p.failed + p.pending;
		if (experiment.status === 'complete' && total > 0) {
			const collisionRate = total > 0 ? Math.round((p.completed / total) * 100) : 0;
			return `${collisionRate}% (${p.completed}/${total})`;
		}
		return `${p.completed}/${total}`;
	}

	function overallProgressPct(): number {
		if (!progress) return 0;
		let completed = 0;
		let total = 0;
		for (const method of experiment.methods) {
			const p = progress[method];
			if (p) {
				completed += p.completed + p.failed;
				total += p.completed + p.failed + p.pending;
			}
		}
		return total > 0 ? (completed / total) * 100 : 0;
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}
</script>

<a href="/experiments/{experiment.id}" class="card">
	<div class="card-header">
		<div class="title-row">
			<h3>{experiment.name}</h3>
			<span class="status-badge" class:running={experiment.status === 'running'} class:complete={experiment.status === 'complete'}>
				{#if experiment.status === 'running'}
					<span class="pulse-dot"></span>
				{/if}
				{statusLabel}
			</span>
		</div>
		<div class="meta">
			<span class="meta-item">{formatDate(experiment.created_at)}</span>
			{#if totalRecords != null}
				<span class="meta-item">{totalRecords} records</span>
			{/if}
		</div>
	</div>

	<div class="methods">
		{#each experiment.methods as method}
			<div class="method-row">
				<span class="method-name">{method}</span>
				<span class="method-stat">{methodProgress(method)}</span>
			</div>
		{/each}
	</div>

	{#if experiment.status === 'running'}
		<div class="progress-track">
			<div class="progress-fill" style="width: {overallProgressPct()}%"></div>
		</div>
	{/if}
</a>

<style>
	.card {
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		padding: 16px;
		text-decoration: none;
		color: inherit;
		transition: transform 0.15s ease, box-shadow 0.15s ease;
		gap: 12px;
	}

	.card:hover {
		transform: translateY(-2px);
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
	}

	.card-header {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.title-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
	}

	h3 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-text);
		line-height: 1.3;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.status-badge {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 0.7rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 4px;
		white-space: nowrap;
		flex-shrink: 0;
		background: rgba(139, 141, 152, 0.15);
		color: var(--color-muted);
	}

	.status-badge.running {
		background: var(--color-accent-dim);
		color: var(--color-accent);
	}

	.status-badge.complete {
		background: rgba(74, 222, 128, 0.12);
		color: #4ade80;
	}

	.pulse-dot {
		display: inline-block;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--color-accent);
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 0.4; }
		50% { opacity: 1; }
	}

	.meta {
		display: flex;
		gap: 12px;
	}

	.meta-item {
		font-size: 0.75rem;
		color: var(--color-muted);
	}

	.methods {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.method-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.method-name {
		font-size: 0.78rem;
		color: var(--color-muted);
		font-family: 'SF Mono', 'Fira Code', monospace;
	}

	.method-stat {
		font-size: 0.78rem;
		color: var(--color-text);
		font-variant-numeric: tabular-nums;
	}

	.progress-track {
		height: 3px;
		background: var(--color-border);
		border-radius: 2px;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: var(--color-accent);
		border-radius: 2px;
		transition: width 0.3s ease;
	}
</style>
