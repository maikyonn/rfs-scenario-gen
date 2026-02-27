<script lang="ts">
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import MetadataPanel from '$lib/components/MetadataPanel.svelte';

	let { data } = $props();
	let scenario = $derived(data.scenario);

	let prevId = $derived(scenario.id > 1 ? scenario.id - 1 : null);
	let nextId = $derived(scenario.id < 100 ? scenario.id + 1 : null);
</script>

<svelte:head>
	<title>#{scenario.id} {scenario.name} - RFS Crash Scenario Viewer</title>
</svelte:head>

<div class="detail">
	<div class="nav-row">
		<a href="/" class="back">&larr; All scenarios</a>
		<div class="prev-next">
			{#if prevId}
				<a href="/scenario/{prevId}" class="nav-link">&larr; #{prevId}</a>
			{/if}
			{#if nextId}
				<a href="/scenario/{nextId}" class="nav-link">#{nextId} &rarr;</a>
			{/if}
		</div>
	</div>

	{#if scenario.videoPath}
		<VideoPlayer src={scenario.videoPath} poster={scenario.thumbnailPath} />
	{:else}
		<div class="no-video">
			<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
				<rect x="2" y="2" width="20" height="20" rx="2" />
				<polygon points="10 8 16 12 10 16 10 8" />
			</svg>
			<span>No video rendered yet</span>
		</div>
	{/if}

	<div class="info">
		<span class="scenario-id">Scenario #{scenario.id}</span>
		<h1>{scenario.name}</h1>
		<p class="description">{scenario.description}</p>
	</div>

	<MetadataPanel {scenario} />

	{#if scenario.xoscPath}
		<div class="actions">
			<a href={scenario.xoscPath} download class="download-btn">
				<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
					<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
					<polyline points="7 10 12 15 17 10" />
					<line x1="12" y1="15" x2="12" y2="3" />
				</svg>
				Download .xosc
			</a>
		</div>
	{/if}
</div>

<style>
	.detail {
		display: flex;
		flex-direction: column;
		gap: 24px;
		max-width: 800px;
	}

	.nav-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.back {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 0.85rem;
		color: var(--color-accent);
		text-decoration: none;
	}

	.back:hover {
		color: var(--color-accent-hover);
	}

	.prev-next {
		display: flex;
		gap: 16px;
	}

	.nav-link {
		font-size: 0.85rem;
		color: var(--color-muted);
		text-decoration: none;
	}

	.nav-link:hover {
		color: var(--color-accent);
	}

	.info {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.scenario-id {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--color-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.description {
		font-size: 0.95rem;
		color: var(--color-muted);
		line-height: 1.6;
	}

	.actions {
		padding-top: 8px;
	}

	.download-btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 10px 20px;
		background: var(--color-accent);
		color: #0f1117;
		font-size: 0.85rem;
		font-weight: 600;
		border-radius: 6px;
		text-decoration: none;
		transition: background 0.15s ease;
	}

	.download-btn:hover {
		background: var(--color-accent-hover);
	}

	.no-video {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 12px;
		aspect-ratio: 16 / 9;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-muted);
		font-size: 0.9rem;
	}
</style>
