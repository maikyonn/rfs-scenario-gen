<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchDatasets } from '$lib/api';
	import type { Dataset } from '$lib/types';

	let datasets = $state<Dataset[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			datasets = await fetchDatasets();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}
</script>

<svelte:head>
	<title>Datasets -- RFS Scenario Workbench</title>
</svelte:head>

<div class="page">
	<div class="page-header">
		<h1>Datasets</h1>
		<p class="subtitle">Crash scenario record collections for evaluation</p>
	</div>

	{#if loading}
		<div class="state-msg">
			<div class="spinner"></div>
			<span>Loading datasets...</span>
		</div>
	{:else if error}
		<div class="state-msg state-error">
			<span>Failed to load datasets: {error}</span>
		</div>
	{:else if datasets.length === 0}
		<div class="state-msg">
			<span>No datasets found. Upload or create a dataset to get started.</span>
		</div>
	{:else}
		<div class="grid">
			{#each datasets as ds (ds.id)}
				<a href="/datasets/{ds.id}" class="card">
					<div class="card-top">
						<h2 class="card-name">{ds.name}</h2>
						{#if ds.source}
							<span class="card-source">{ds.source}</span>
						{/if}
					</div>
					<div class="card-bottom">
						<span class="card-count">
							<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
								<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
								<polyline points="14 2 14 8 20 8" />
								<line x1="16" y1="13" x2="8" y2="13" />
								<line x1="16" y1="17" x2="8" y2="17" />
							</svg>
							{ds.record_count} record{ds.record_count !== 1 ? 's' : ''}
						</span>
						<span class="card-date">{formatDate(ds.created_at)}</span>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.page-header {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.page-header h1 {
		font-size: 1.5rem;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.subtitle {
		font-size: 0.9rem;
		color: var(--color-muted);
	}

	/* ── States ── */
	.state-msg {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 40px 0;
		justify-content: center;
		color: var(--color-muted);
		font-size: 0.9rem;
	}

	.state-error {
		color: #f87171;
	}

	.spinner {
		width: 18px;
		height: 18px;
		border: 2px solid var(--color-border);
		border-top-color: var(--color-accent);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* ── Card grid ── */
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 16px;
	}

	.card {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 16px;
		padding: 20px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 10px;
		text-decoration: none;
		color: var(--color-text);
		transition:
			border-color 0.15s,
			background 0.15s;
	}

	.card:hover {
		border-color: rgba(96, 165, 250, 0.4);
		background: rgba(26, 29, 39, 0.8);
	}

	.card-top {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.card-name {
		font-size: 1.05rem;
		font-weight: 600;
		letter-spacing: -0.01em;
	}

	.card-source {
		font-size: 0.78rem;
		color: var(--color-muted);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--color-border);
		border-radius: 4px;
		padding: 2px 8px;
		display: inline-block;
		width: fit-content;
	}

	.card-bottom {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.card-count {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 0.82rem;
		color: var(--color-accent);
		font-weight: 500;
	}

	.card-date {
		font-size: 0.78rem;
		color: var(--color-muted);
	}
</style>
