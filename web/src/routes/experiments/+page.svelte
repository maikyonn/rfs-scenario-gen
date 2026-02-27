<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchExperiments, fetchExperiment, fetchDatasets } from '$lib/api';
	import type { Experiment, ExperimentProgress, Dataset } from '$lib/types';
	import ExperimentCard from '$lib/components/ExperimentCard.svelte';
	import NewExperimentDialog from '$lib/components/NewExperimentDialog.svelte';

	let experiments = $state<Experiment[]>([]);
	let progressMap = $state<Record<number, ExperimentProgress>>({});
	let datasets = $state<Dataset[]>([]);
	let loading = $state(true);
	let error = $state('');
	let showDialog = $state(false);
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		loadExperiments();
		loadDatasets();

		refreshTimer = setInterval(refreshRunning, 5000);

		return () => {
			if (refreshTimer) clearInterval(refreshTimer);
		};
	});

	async function loadExperiments() {
		loading = true;
		error = '';
		try {
			experiments = await fetchExperiments();
			await fetchProgressForRunning();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function loadDatasets() {
		try {
			datasets = await fetchDatasets();
		} catch {
			// non-critical
		}
	}

	async function fetchProgressForRunning() {
		const running = experiments.filter(e => e.status === 'running');
		for (const exp of running) {
			try {
				const detail = await fetchExperiment(exp.id);
				progressMap[exp.id] = detail.progress;
			} catch {
				// ignore individual failures
			}
		}
	}

	async function refreshRunning() {
		const running = experiments.filter(e => e.status === 'running');
		if (running.length === 0) return;

		for (const exp of running) {
			try {
				const detail = await fetchExperiment(exp.id);
				progressMap[exp.id] = detail.progress;
				// Update status in case it completed
				if (detail.status !== exp.status) {
					exp.status = detail.status;
				}
			} catch {
				// ignore
			}
		}
	}

	function handleCreated() {
		showDialog = false;
		loadExperiments();
	}
</script>

<svelte:head>
	<title>Experiments -- RFS</title>
</svelte:head>

<div class="page">
	<div class="page-header">
		<h1>Experiments</h1>
		<button class="btn-new" onclick={() => { showDialog = true; }}>
			+ New Experiment
		</button>
	</div>

	{#if loading}
		<div class="state-msg">Loading experiments...</div>
	{:else if error}
		<div class="state-msg state-error">{error}</div>
	{:else if experiments.length === 0}
		<div class="empty-state">
			<p>No experiments yet.</p>
			<p class="empty-hint">Create one to compare generation methods on a dataset.</p>
		</div>
	{:else}
		<div class="grid">
			{#each experiments as exp (exp.id)}
				<ExperimentCard
					experiment={exp}
					progress={progressMap[exp.id] ?? null}
				/>
			{/each}
		</div>
	{/if}
</div>

{#if showDialog}
	<NewExperimentDialog
		{datasets}
		oncreated={handleCreated}
	/>
{/if}

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}

	h1 {
		margin: 0;
		font-size: 1.4rem;
		font-weight: 700;
		color: var(--color-text);
	}

	.btn-new {
		padding: 8px 16px;
		border-radius: 6px;
		font-size: 0.85rem;
		font-weight: 600;
		border: 1px solid rgba(96, 165, 250, 0.3);
		background: var(--color-accent-dim);
		color: var(--color-accent);
		cursor: pointer;
		transition: background 0.15s, color 0.15s;
	}

	.btn-new:hover {
		background: rgba(96, 165, 250, 0.2);
		color: var(--color-accent-hover);
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
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

	.empty-state {
		text-align: center;
		padding: 64px 0;
	}

	.empty-state p {
		margin: 0;
		font-size: 0.95rem;
		color: var(--color-muted);
	}

	.empty-hint {
		margin-top: 6px;
		font-size: 0.82rem;
		color: var(--color-muted);
		opacity: 0.7;
	}
</style>
