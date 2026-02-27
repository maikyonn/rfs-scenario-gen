<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { fetchDatasetStats, fetchRecords } from '$lib/api';
	import type { DatasetRecord, DatasetStats } from '$lib/types';

	const PER_PAGE = 20;

	// ── Crash-type color palette ─────────────────────────────────────────────
	const CRASH_COLORS: Record<string, string> = {
		'rear_end': '#f59e0b',
		'head_on': '#ef4444',
		'sideswipe': '#a78bfa',
		'junction': '#60a5fa',
		'pedestrian': '#34d399',
		'dooring': '#fb923c',
		'parking': '#94a3b8',
		'motorcycle': '#f472b6',
	};

	function crashColor(type: string): string {
		return CRASH_COLORS[type] ?? '#8b8d98';
	}

	// ── State ────────────────────────────────────────────────────────────────

	let datasetId = $derived(Number(page.params.id));

	let stats = $state<DatasetStats | null>(null);
	let records = $state<DatasetRecord[]>([]);
	let totalRecords = $state(0);
	let currentPage = $state(1);
	let totalPages = $derived(Math.max(1, Math.ceil(totalRecords / PER_PAGE)));

	let activeCrashType = $state<string | null>(null);
	let searchQuery = $state('');
	let searchInput = $state('');
	let searchTimeout = $state<ReturnType<typeof setTimeout> | null>(null);

	let loadingStats = $state(true);
	let loadingRecords = $state(true);
	let error = $state<string | null>(null);

	let expandedIds = $state<Set<number>>(new Set());

	// ── Data fetching ────────────────────────────────────────────────────────

	onMount(() => {
		loadStats();
		loadRecords();
	});

	async function loadStats() {
		loadingStats = true;
		try {
			stats = await fetchDatasetStats(datasetId);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loadingStats = false;
		}
	}

	async function loadRecords() {
		loadingRecords = true;
		try {
			const res = await fetchRecords(datasetId, {
				page: currentPage,
				per_page: PER_PAGE,
				crash_type: activeCrashType ?? undefined,
				search: searchQuery || undefined
			});
			records = res.records;
			totalRecords = res.total;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loadingRecords = false;
		}
	}

	// ── Filters & pagination ─────────────────────────────────────────────────

	function selectCrashType(type: string | null) {
		activeCrashType = type;
		currentPage = 1;
		loadRecords();
	}

	function handleSearchInput(e: Event) {
		const value = (e.target as HTMLInputElement).value;
		searchInput = value;
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			searchQuery = value.trim();
			currentPage = 1;
			loadRecords();
		}, 350);
	}

	function goToPage(p: number) {
		if (p < 1 || p > totalPages) return;
		currentPage = p;
		loadRecords();
	}

	function toggleExpand(id: number) {
		const next = new Set(expandedIds);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		expandedIds = next;
	}

	function truncate(text: string, max: number): { text: string; truncated: boolean } {
		if (text.length <= max) return { text, truncated: false };
		return { text: text.slice(0, max) + '...', truncated: true };
	}

	// ── Sorted crash types for filter bar ────────────────────────────────────

	let sortedCrashTypes = $derived(
		stats
			? Object.entries(stats.by_crash_type).sort((a, b) => b[1] - a[1])
			: []
	);

	// ── Generation status helpers ────────────────────────────────────────────

	function genStatusClass(gen: { status: string; collision_detected: boolean | null } | null): string {
		if (!gen) return 'gen-none';
		if (gen.status === 'failed') return 'gen-fail';
		if (gen.collision_detected === true) return 'gen-pass';
		if (gen.collision_detected === false) return 'gen-nocollision';
		return 'gen-pending';
	}

	function genStatusLabel(gen: { status: string; collision_detected: boolean | null } | null): string {
		if (!gen) return 'not run';
		if (gen.status === 'failed') return 'failed';
		if (gen.collision_detected === true) return 'collision';
		if (gen.collision_detected === false) return 'no collision';
		return gen.status;
	}
</script>

<svelte:head>
	<title>Dataset #{datasetId} -- RFS Scenario Workbench</title>
</svelte:head>

<div class="page">
	<!-- ── Back link + header ──────────────────────────────────────────────── -->
	<a href="/datasets" class="back-link">&larr; All datasets</a>

	{#if error}
		<div class="state-msg state-error">Failed to load: {error}</div>
	{/if}

	<div class="header-row">
		<div class="header-text">
			<h1>Dataset #{datasetId}</h1>
			{#if stats}
				<span class="record-total">{stats.total} record{stats.total !== 1 ? 's' : ''}</span>
			{/if}
		</div>
	</div>

	<!-- ── Crash-type filter bar ──────────────────────────────────────────── -->
	{#if !loadingStats && stats && sortedCrashTypes.length > 0}
		<div class="filter-bar">
			<button
				class="filter-btn"
				class:active={activeCrashType === null}
				onclick={() => selectCrashType(null)}
			>
				All
				<span class="filter-count">{stats.total}</span>
			</button>
			{#each sortedCrashTypes as [type, count]}
				<button
					class="filter-btn"
					class:active={activeCrashType === type}
					onclick={() => selectCrashType(type)}
					style="--type-color: {crashColor(type)}"
				>
					<span class="filter-dot" style="background: {crashColor(type)}"></span>
					{type.replace(/_/g, ' ')}
					<span class="filter-count">{count}</span>
				</button>
			{/each}
		</div>
	{/if}

	<!-- ── Search ─────────────────────────────────────────────────────────── -->
	<div class="search-row">
		<div class="search-input-wrap">
			<svg class="search-icon" xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<circle cx="11" cy="11" r="8" />
				<line x1="21" y1="21" x2="16.65" y2="16.65" />
			</svg>
			<input
				type="text"
				placeholder="Search descriptions..."
				value={searchInput}
				oninput={handleSearchInput}
			/>
		</div>
		{#if !loadingRecords}
			<span class="results-count">
				{totalRecords} result{totalRecords !== 1 ? 's' : ''}
			</span>
		{/if}
	</div>

	<!-- ── Record list ────────────────────────────────────────────────────── -->
	{#if loadingRecords && records.length === 0}
		<div class="state-msg">
			<div class="spinner"></div>
			<span>Loading records...</span>
		</div>
	{:else if records.length === 0}
		<div class="state-msg">No records match the current filters.</div>
	{:else}
		<div class="record-list" class:loading-overlay={loadingRecords}>
			{#each records as rec (rec.id)}
				{@const desc = truncate(rec.text_desc, 200)}
				{@const isExpanded = expandedIds.has(rec.id)}
				<div class="record-card">
					<div class="record-top">
						<span class="crash-badge" style="--badge-color: {crashColor(rec.crash_type)}">
							{rec.crash_type.replace(/_/g, ' ')}
						</span>
						<span class="pattern-label">{rec.pattern.replace(/_/g, ' ')}</span>
						<span class="record-id">#{rec.id}</span>
					</div>

					<div class="record-desc">
						{#if isExpanded || !desc.truncated}
							<p>{rec.text_desc}</p>
						{:else}
							<p>{desc.text}</p>
						{/if}
						{#if desc.truncated}
							<button class="expand-btn" onclick={() => toggleExpand(rec.id)}>
								{isExpanded ? 'Show less' : 'Show more'}
							</button>
						{/if}
					</div>

					{#if Object.keys(rec.generations).length > 0}
						<div class="gen-row">
							{#each Object.entries(rec.generations) as [method, gen]}
								<span class="gen-chip {genStatusClass(gen)}" title="{method}: {genStatusLabel(gen)}">
									{method}
								</span>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- ── Pagination ─────────────────────────────────────────────────── -->
		{#if totalPages > 1}
			<div class="pagination">
				<button
					class="page-btn"
					disabled={currentPage <= 1}
					onclick={() => goToPage(currentPage - 1)}
				>
					Prev
				</button>
				<span class="page-info">Page {currentPage} of {totalPages}</span>
				<button
					class="page-btn"
					disabled={currentPage >= totalPages}
					onclick={() => goToPage(currentPage + 1)}
				>
					Next
				</button>
			</div>
		{/if}
	{/if}
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	/* ── Back link ── */
	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 0.85rem;
		color: var(--color-accent);
		text-decoration: none;
		width: fit-content;
	}

	.back-link:hover {
		color: var(--color-accent-hover);
	}

	/* ── Header ── */
	.header-row {
		display: flex;
		align-items: baseline;
		gap: 16px;
	}

	.header-text {
		display: flex;
		align-items: baseline;
		gap: 12px;
	}

	.header-text h1 {
		font-size: 1.5rem;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.record-total {
		font-size: 0.85rem;
		color: var(--color-muted);
		font-weight: 500;
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
		padding: 12px 0;
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

	/* ── Filter bar ── */
	.filter-bar {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.filter-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 5px 12px;
		border-radius: 20px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		transition:
			color 0.15s,
			border-color 0.15s,
			background 0.15s;
		white-space: nowrap;
	}

	.filter-btn:hover {
		color: var(--color-text);
		border-color: rgba(255, 255, 255, 0.15);
	}

	.filter-btn.active {
		color: var(--color-accent);
		border-color: rgba(96, 165, 250, 0.4);
		background: var(--color-accent-dim);
	}

	.filter-dot {
		display: inline-block;
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.filter-count {
		font-size: 0.72rem;
		color: var(--color-muted);
		font-weight: 400;
	}

	/* ── Search ── */
	.search-row {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.search-input-wrap {
		flex: 1;
		position: relative;
		max-width: 400px;
	}

	.search-icon {
		position: absolute;
		left: 10px;
		top: 50%;
		transform: translateY(-50%);
		color: var(--color-muted);
		pointer-events: none;
	}

	.search-input-wrap input {
		width: 100%;
		padding: 8px 12px 8px 32px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-text);
		font-family: inherit;
		font-size: 0.85rem;
		transition: border-color 0.15s;
	}

	.search-input-wrap input:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	.search-input-wrap input::placeholder {
		color: var(--color-muted);
	}

	.results-count {
		font-size: 0.8rem;
		color: var(--color-muted);
		white-space: nowrap;
	}

	/* ── Record list ── */
	.record-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
		transition: opacity 0.15s;
	}

	.record-list.loading-overlay {
		opacity: 0.5;
		pointer-events: none;
	}

	.record-card {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 14px 18px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		transition: border-color 0.15s;
	}

	.record-card:hover {
		border-color: rgba(255, 255, 255, 0.1);
	}

	.record-top {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}

	.crash-badge {
		display: inline-flex;
		align-items: center;
		padding: 2px 9px;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: capitalize;
		background: color-mix(in srgb, var(--badge-color) 15%, transparent);
		color: var(--badge-color);
		border: 1px solid color-mix(in srgb, var(--badge-color) 30%, transparent);
		letter-spacing: 0.01em;
	}

	.pattern-label {
		font-size: 0.78rem;
		color: var(--color-muted);
		text-transform: capitalize;
	}

	.record-id {
		margin-left: auto;
		font-size: 0.72rem;
		color: var(--color-muted);
		font-family: 'SF Mono', 'Fira Code', monospace;
	}

	.record-desc p {
		font-size: 0.88rem;
		line-height: 1.55;
		color: var(--color-text);
		margin: 0;
	}

	.expand-btn {
		background: none;
		border: none;
		padding: 0;
		margin-top: 2px;
		color: var(--color-accent);
		font-size: 0.78rem;
		cursor: pointer;
		font-family: inherit;
	}

	.expand-btn:hover {
		color: var(--color-accent-hover);
	}

	/* ── Generation status chips ── */
	.gen-row {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
		padding-top: 4px;
	}

	.gen-chip {
		display: inline-flex;
		align-items: center;
		padding: 2px 8px;
		border-radius: 4px;
		font-size: 0.7rem;
		font-weight: 500;
		font-family: 'SF Mono', 'Fira Code', monospace;
		letter-spacing: 0.02em;
	}

	.gen-none {
		background: rgba(255, 255, 255, 0.03);
		color: var(--color-muted);
		border: 1px solid var(--color-border);
	}

	.gen-pass {
		background: rgba(52, 211, 153, 0.12);
		color: #34d399;
		border: 1px solid rgba(52, 211, 153, 0.3);
	}

	.gen-nocollision {
		background: rgba(251, 146, 60, 0.12);
		color: #fb923c;
		border: 1px solid rgba(251, 146, 60, 0.3);
	}

	.gen-fail {
		background: rgba(248, 113, 113, 0.12);
		color: #f87171;
		border: 1px solid rgba(248, 113, 113, 0.3);
	}

	.gen-pending {
		background: rgba(96, 165, 250, 0.1);
		color: var(--color-accent);
		border: 1px solid rgba(96, 165, 250, 0.25);
	}

	/* ── Pagination ── */
	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 16px;
		padding: 8px 0 4px;
	}

	.page-btn {
		padding: 6px 16px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-text);
		font-size: 0.82rem;
		font-weight: 500;
		cursor: pointer;
		font-family: inherit;
		transition:
			border-color 0.15s,
			color 0.15s;
	}

	.page-btn:hover:not(:disabled) {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}

	.page-btn:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}

	.page-info {
		font-size: 0.82rem;
		color: var(--color-muted);
	}
</style>
