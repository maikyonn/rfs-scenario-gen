<script lang="ts">
	import { fly } from 'svelte/transition';

	let { name, input, output, status, subStatus }: {
		name: string;
		input: unknown;
		output?: unknown;
		status: 'running' | 'done' | 'error';
		subStatus?: string;
	} = $props();

	// ── Display names ──────────────────────────────────────────────────────────

	const DISPLAY_NAMES: Record<string, string> = {
		generate_crash_config: 'Generate scenario config',
		modify_config:         'Modify config',
		build_scenario:        'Build .xosc file',
		validate_collision:    'Validate collision',
		render_scenario:       'Render video',
	};

	// ── Tool icons (inline SVG paths) ──────────────────────────────────────────

	const ICONS: Record<string, string> = {
		generate_crash_config: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
		modify_config:         'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
		build_scenario:        'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4',
		validate_collision:    'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
		render_scenario:       'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z',
	};

	// ── Fallback cycling messages ──────────────────────────────────────────────

	const FALLBACK: Record<string, string[]> = {
		generate_crash_config: ['Sending to Claude Sonnet…', 'Selecting crash pattern…', 'Configuring entities…'],
		modify_config:         ['Sending modification…', 'Applying changes…'],
		build_scenario:        ['Running ConfigBuilder…', 'Writing OpenSCENARIO XML…'],
		validate_collision:    ['Launching esmini…', 'Running physics simulation…', 'Checking collisions…'],
		render_scenario:       ['Starting esmini renderer…', 'Capturing frames…', 'Encoding with ffmpeg…'],
	};

	// ── Elapsed timer ──────────────────────────────────────────────────────────

	let elapsed = $state(0);
	let finalElapsed = $state<number | null>(null);
	let timerHandle: ReturnType<typeof setInterval> | null = null;

	$effect(() => {
		if (status === 'running') {
			elapsed = 0;
			timerHandle = setInterval(() => { elapsed += 1; }, 1000);
		} else {
			if (timerHandle !== null) {
				clearInterval(timerHandle);
				timerHandle = null;
				finalElapsed = elapsed;
			}
		}
		return () => {
			if (timerHandle !== null) clearInterval(timerHandle);
		};
	});

	function fmtElapsed(s: number): string {
		return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
	}

	// ── Fallback cycling sub-status ────────────────────────────────────────────

	let fallbackIdx = $state(0);
	let fallbackHandle: ReturnType<typeof setInterval> | null = null;

	$effect(() => {
		if (status === 'running' && !subStatus) {
			const msgs = FALLBACK[name] ?? [];
			if (msgs.length > 1) {
				fallbackHandle = setInterval(() => {
					fallbackIdx = (fallbackIdx + 1) % msgs.length;
				}, 3000);
			}
		} else {
			if (fallbackHandle !== null) {
				clearInterval(fallbackHandle);
				fallbackHandle = null;
			}
			fallbackIdx = 0;
		}
		return () => {
			if (fallbackHandle !== null) clearInterval(fallbackHandle);
		};
	});

	const activeSub = $derived(
		subStatus
			? subStatus
			: status === 'running'
				? (FALLBACK[name]?.[fallbackIdx] ?? '')
				: ''
	);

	// ── Input preview ──────────────────────────────────────────────────────────

	const inputPreview = $derived((() => {
		if (input == null) return '';
		const vals = typeof input === 'object' ? Object.values(input as Record<string, unknown>) : [input];
		const first = vals.find(v => typeof v === 'string') as string | undefined;
		if (!first) return '';
		return first.length > 55 ? first.slice(0, 52) + '…' : first;
	})());

	// ── Output summary ─────────────────────────────────────────────────────────

	function outputSummary(): string {
		if (status !== 'done' || output == null) return '';
		const o = output as Record<string, unknown>;

		if (name === 'validate_collision') {
			if (o.collision_detected) {
				const t = o.collision_time != null ? ` at ${(o.collision_time as number).toFixed(2)}s` : '';
				return `Collision confirmed${t}`;
			}
			return 'No collision detected';
		}
		if (name === 'render_scenario') {
			return o.mp4_url ? 'Video ready' : `Error: ${o.error}`;
		}
		if (name === 'build_scenario') {
			return o.error ? `Error: ${o.error}` : '.xosc written';
		}
		if (name === 'generate_crash_config' || name === 'modify_config') {
			const raw = typeof output === 'string' ? output : JSON.stringify(output);
			if (raw.startsWith('ERROR:')) return raw.slice(0, 60);
			const cfg = typeof output === 'object' ? output as Record<string, unknown> : null;
			const pattern = cfg?.pattern as string | undefined;
			const entities = Array.isArray(cfg?.entities) ? (cfg.entities as unknown[]).length : null;
			return pattern
				? `Pattern: ${pattern}${entities != null ? ` · ${entities} entities` : ''}`
				: 'Config ready';
		}
		return 'Done';
	}

	// ── Done-flash trigger ─────────────────────────────────────────────────────

	let justDone = $state(false);
	let prevStatus = $state(status);

	$effect(() => {
		if (prevStatus === 'running' && status === 'done') {
			justDone = true;
			setTimeout(() => { justDone = false; }, 700);
		}
		prevStatus = status;
	});

	// ── Details toggle ─────────────────────────────────────────────────────────

	const detailsJson = $derived(
		JSON.stringify({ input, output }, null, 2)
	);

	const displayName = $derived(DISPLAY_NAMES[name] ?? name);
	const iconPath = $derived(ICONS[name] ?? 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z');
	const elapsedDisplay = $derived(
		status === 'running' ? fmtElapsed(elapsed) : finalElapsed != null ? fmtElapsed(finalElapsed) : null
	);
</script>

<div
	class="tool-card"
	class:running={status === 'running'}
	class:done={status === 'done'}
	class:error={status === 'error'}
	class:just-done={justDone}
	in:fly={{ y: 8, opacity: 0, duration: 200 }}
>
	<!-- Accent bar -->
	<div class="accent-bar" class:pulse={status === 'running'} class:bar-done={status === 'done'} class:bar-error={status === 'error'}></div>

	<!-- Main content -->
	<div class="card-body">
		<div class="card-header">
			<div class="header-left">
				<!-- Icon -->
				<svg class="tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
					<path d={iconPath}/>
				</svg>
				<span class="tool-name">{displayName}</span>
			</div>

			<!-- Right: timer + status icon -->
			<div class="header-right">
				{#if elapsedDisplay}
					<span class="timer" class:timer-running={status === 'running'}>⏱ {elapsedDisplay}</span>
				{/if}
				{#if status === 'running'}
					<span class="spinner"></span>
				{:else if status === 'done'}
					<svg class="status-icon icon-done" viewBox="0 0 16 16" fill="none">
						<path d="M3 8l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
					</svg>
				{:else}
					<svg class="status-icon icon-error" viewBox="0 0 16 16" fill="none">
						<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
					</svg>
				{/if}
			</div>
		</div>

		<!-- Input preview -->
		{#if inputPreview}
			<div class="sub-line input-preview">↳ {inputPreview}</div>
		{/if}

		<!-- Sub-status / output summary -->
		{#if status === 'running' && activeSub}
			<div class="sub-line sub-status">{activeSub}</div>
		{:else if status === 'done'}
			<div class="sub-line output-line">{outputSummary()}</div>
		{/if}

		<!-- Expandable details -->
		<details class="details">
			<summary class="details-toggle">↓ details</summary>
			<pre class="details-pre">{detailsJson}</pre>
		</details>
	</div>
</div>

<style>
	.tool-card {
		display: flex;
		border-radius: 7px;
		border: 1px solid var(--color-border);
		background: var(--color-bg);
		margin: 3px 0;
		overflow: hidden;
		transition: background 0.6s ease;
	}

	.tool-card.running {
		border-color: rgba(96, 165, 250, 0.3);
		background: rgba(96, 165, 250, 0.04);
	}

	.tool-card.done {
		border-color: rgba(74, 222, 128, 0.2);
		background: rgba(74, 222, 128, 0.03);
	}

	.tool-card.error {
		border-color: rgba(248, 113, 113, 0.3);
		background: rgba(248, 113, 113, 0.04);
	}

	/* Flash green when transitioning to done */
	.tool-card.just-done {
		background: rgba(74, 222, 128, 0.10);
	}

	/* ── Accent bar ── */
	.accent-bar {
		width: 3px;
		flex-shrink: 0;
		background: var(--color-border);
		transition: background 0.4s ease;
	}

	.accent-bar.bar-done {
		background: #4ade80;
	}

	.accent-bar.bar-error {
		background: #f87171;
	}

	.accent-bar.pulse {
		animation: pulse-bar 1.6s ease-in-out infinite;
	}

	@keyframes pulse-bar {
		0%, 100% { background: rgba(96, 165, 250, 0.4); }
		50%       { background: rgba(96, 165, 250, 1); }
	}

	/* ── Body ── */
	.card-body {
		flex: 1;
		padding: 8px 10px 6px 10px;
		display: flex;
		flex-direction: column;
		gap: 3px;
		min-width: 0;
	}

	.card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-shrink: 0;
	}

	.tool-icon {
		width: 14px;
		height: 14px;
		flex-shrink: 0;
		color: var(--color-muted);
	}

	.tool-name {
		font-size: 0.83rem;
		font-weight: 500;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* ── Timer ── */
	.timer {
		font-size: 0.72rem;
		color: var(--color-muted);
		font-variant-numeric: tabular-nums;
	}

	.timer.timer-running {
		color: var(--color-accent);
	}

	/* ── Status icon ── */
	.status-icon {
		width: 13px;
		height: 13px;
		flex-shrink: 0;
	}

	.icon-done  { color: #4ade80; }
	.icon-error { color: #f87171; }

	/* ── Sub-lines ── */
	.sub-line {
		font-size: 0.76rem;
		line-height: 1.4;
		padding-left: 20px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.input-preview {
		color: var(--color-muted);
	}

	.sub-status {
		color: var(--color-accent);
	}

	.output-line {
		color: rgba(74, 222, 128, 0.85);
	}

	/* ── Spinner ── */
	.spinner {
		display: inline-block;
		width: 11px;
		height: 11px;
		border: 2px solid rgba(96, 165, 250, 0.2);
		border-top-color: var(--color-accent);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
		flex-shrink: 0;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* ── Expandable details ── */
	.details {
		margin-top: 2px;
	}

	.details-toggle {
		font-size: 0.7rem;
		color: var(--color-muted);
		cursor: pointer;
		user-select: none;
		list-style: none;
		padding-left: 20px;
	}

	.details-toggle::-webkit-details-marker { display: none; }

	.details-toggle:hover {
		color: var(--color-accent);
	}

	.details-pre {
		margin: 4px 0 0 0;
		padding: 8px;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 4px;
		font-size: 0.7rem;
		line-height: 1.45;
		color: var(--color-muted);
		overflow-x: auto;
		white-space: pre;
		max-height: 200px;
		overflow-y: auto;
	}
</style>
