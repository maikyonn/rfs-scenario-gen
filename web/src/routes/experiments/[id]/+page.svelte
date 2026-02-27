<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import {
		fetchExperiment,
		fetchExperimentSummary,
		fetchExperimentResults
	} from '$lib/api';
	import type {
		ExperimentDetail,
		ExperimentSummary,
		ExperimentResult
	} from '$lib/types';
	import SummaryTable from '$lib/components/SummaryTable.svelte';
	import SideBySideView from '$lib/components/SideBySideView.svelte';

	// ── State ──────────────────────────────────────────────────────────────────

	let experimentId = $derived(Number(page.params.id));

	let experiment = $state<ExperimentDetail | null>(null);
	let summary = $state<ExperimentSummary | null>(null);
	let results = $state<ExperimentResult[]>([]);
	let resultsTotal = $state(0);
	let resultsPage = $state(1);
	const resultsPerPage = 5;

	let loading = $state(true);
	let error = $state('');
	let activeTab = $state<'summary' | 'side-by-side'>('summary');
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	// ── Derived ────────────────────────────────────────────────────────────────

	const isRunning = $derived(experiment?.status === 'running');
	const methods = $derived(experiment?.methods ?? []);
	const totalPages = $derived(Math.max(1, Math.ceil(resultsTotal / resultsPerPage)));

	const overallProgress = $derived((() => {
		if (!experiment?.progress) return { completed: 0, total: 0, pct: 0 };
		let completed = 0;
		let total = 0;
		for (const m of methods) {
			const p = experiment.progress[m];
			if (p) {
				completed += p.completed + p.failed;
				total += p.completed + p.failed + p.pending;
			}
		}
		return { completed, total, pct: total > 0 ? (completed / total) * 100 : 0 };
	})());

	// ── Lifecycle ──────────────────────────────────────────────────────────────

	onMount(() => {
		loadExperiment();

		refreshTimer = setInterval(() => {
			if (isRunning) refreshExperiment();
		}, 5000);

		return () => {
			if (refreshTimer) clearInterval(refreshTimer);
		};
	});

	async function loadExperiment() {
		loading = true;
		error = '';
		try {
			experiment = await fetchExperiment(experimentId);
			if (experiment.status === 'complete') {
				summary = await fetchExperimentSummary(experimentId);
			}
			await loadResults();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function refreshExperiment() {
		try {
			const detail = await fetchExperiment(experimentId);
			experiment = detail;
			if (detail.status === 'complete' && !summary) {
				summary = await fetchExperimentSummary(experimentId);
			}
		} catch {
			// ignore refresh errors
		}
	}

	async function loadResults() {
		try {
			const res = await fetchExperimentResults(experimentId, {
				page: resultsPage,
				per_page: resultsPerPage
			});
			results = res.results;
			resultsTotal = res.total;
		} catch {
			// non-critical
		}
	}

	async function goToPage(p: number) {
		if (p < 1 || p > totalPages) return;
		resultsPage = p;
		await loadResults();
	}

	function statusLabel(status: string): string {
		if (status === 'running') return 'Running';
		if (status === 'complete') return 'Complete';
		return 'Pending';
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>{experiment?.name ?? 'Experiment'} -- RFS</title>
</svelte:head>

<div class="page">
	{#if loading}
		<div class="state-msg">Loading experiment...</div>
	{:else if error}
		<div class="state-msg state-error">{error}</div>
	{:else if experiment}
		<!-- Header -->
		<div class="exp-header">
			<div class="header-left">
				<a href="/experiments" class="back-link">Experiments</a>
				<span class="back-sep">/</span>
				<h1>{experiment.name}</h1>
			</div>
			<span
				class="status-badge"
				class:running={experiment.status === 'running'}
				class:complete={experiment.status === 'complete'}
			>
				{#if experiment.status === 'running'}
					<span class="pulse-dot"></span>
				{/if}
				{statusLabel(experiment.status)}
			</span>
		</div>

		<!-- Progress info -->
		<div class="progress-info">
			<span class="meta-item">Created {formatDate(experiment.created_at)}</span>
			<span class="meta-item">{experiment.total} records</span>
			<span class="meta-item">{methods.length} method{methods.length !== 1 ? 's' : ''}</span>
			{#if isRunning}
				<span class="meta-item meta-progress">
					{overallProgress.completed}/{overallProgress.total} done ({Math.round(overallProgress.pct)}%)
				</span>
			{/if}
		</div>

		{#if isRunning}
			<div class="progress-track">
				<div class="progress-fill" style="width: {overallProgress.pct}%"></div>
			</div>
		{/if}

		<!-- Tab bar -->
		<div class="tabs">
			<button
				class="tab"
				class:active={activeTab === 'summary'}
				onclick={() => { activeTab = 'summary'; }}
			>
				Summary
			</button>
			<button
				class="tab"
				class:active={activeTab === 'side-by-side'}
				onclick={() => { activeTab = 'side-by-side'; if (results.length === 0) loadResults(); }}
			>
				Side-by-Side
			</button>
		</div>

		<!-- Tab content -->
		{#if activeTab === 'summary'}
			<div class="tab-content">
				{#if summary && methods.length > 0}
					<SummaryTable {summary} {methods} />
				{:else if experiment.status === 'complete'}
					<div class="state-msg">No summary data available.</div>
				{:else}
					<div class="state-msg">Summary will be available once the experiment completes.</div>
				{/if}
			</div>
		{:else}
			<div class="tab-content">
				{#if results.length === 0}
					<div class="state-msg">No results available yet.</div>
				{:else}
					<div class="results-list">
						{#each results as result (result.record.id)}
							<SideBySideView {result} {methods} />
						{/each}
					</div>

					<!-- Pagination -->
					{#if totalPages > 1}
						<div class="pagination">
							<button
								class="page-btn"
								disabled={resultsPage <= 1}
								onclick={() => goToPage(resultsPage - 1)}
							>
								Prev
							</button>
							<span class="page-info">
								{resultsPage} / {totalPages}
							</span>
							<button
								class="page-btn"
								disabled={resultsPage >= totalPages}
								onclick={() => goToPage(resultsPage + 1)}
							>
								Next
							</button>
						</div>
					{/if}
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.state-msg {
		text-align: center;
		padding: 48px 0;
		color: var(--color-muted);
		font-size: 0.9rem;
	}

	.state-error {
		color: #f87171;
	}

	/* ── Header ── */
	.exp-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.back-link {
		font-size: 0.85rem;
		color: var(--color-muted);
		text-decoration: none;
		flex-shrink: 0;
	}

	.back-link:hover {
		color: var(--color-accent);
	}

	.back-sep {
		color: var(--color-border);
		font-size: 0.85rem;
	}

	h1 {
		margin: 0;
		font-size: 1.3rem;
		font-weight: 700;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.status-badge {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 0.72rem;
		font-weight: 600;
		padding: 3px 10px;
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

	/* ── Progress info ── */
	.progress-info {
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
	}

	.meta-item {
		font-size: 0.78rem;
		color: var(--color-muted);
	}

	.meta-progress {
		color: var(--color-accent);
		font-weight: 500;
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

	/* ── Tabs ── */
	.tabs {
		display: flex;
		gap: 0;
		border-bottom: 1px solid var(--color-border);
	}

	.tab {
		padding: 10px 20px;
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-muted);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		cursor: pointer;
		transition: color 0.15s, border-color 0.15s;
		margin-bottom: -1px;
	}

	.tab:hover {
		color: var(--color-text);
	}

	.tab.active {
		color: var(--color-accent);
		border-bottom-color: var(--color-accent);
	}

	/* ── Tab content ── */
	.tab-content {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.results-list {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	/* ── Pagination ── */
	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 16px 0;
	}

	.page-btn {
		padding: 6px 14px;
		border-radius: 6px;
		font-size: 0.82rem;
		font-weight: 500;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		cursor: pointer;
		transition: color 0.15s, border-color 0.15s;
	}

	.page-btn:hover:not(:disabled) {
		color: var(--color-accent);
		border-color: rgba(96, 165, 250, 0.4);
	}

	.page-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.page-info {
		font-size: 0.82rem;
		color: var(--color-muted);
		font-variant-numeric: tabular-nums;
	}
</style>
