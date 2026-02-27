<script lang="ts">
	import type { Dataset } from '$lib/types';
	import { createExperiment } from '$lib/api';

	let { datasets, oncreated }: {
		datasets: Dataset[];
		oncreated: () => void;
	} = $props();

	let name = $state('');
	let datasetId = $state<number | null>(null);
	let crashTypeFilter = $state('');
	let maxRecords = $state(50);
	let methodPatternBased = $state(true);
	let methodFromScratch = $state(true);
	let submitting = $state(false);
	let error = $state('');

	function close() {
		oncreated();
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			close();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			close();
		}
	}

	async function handleSubmit() {
		if (!name.trim() || datasetId == null) return;
		const methods: string[] = [];
		if (methodPatternBased) methods.push('pattern_based');
		if (methodFromScratch) methods.push('from_scratch');
		if (methods.length === 0) {
			error = 'Select at least one method.';
			return;
		}

		submitting = true;
		error = '';

		try {
			await createExperiment({
				name: name.trim(),
				dataset_id: datasetId,
				methods,
				crash_type_filter: crashTypeFilter.trim() || undefined,
				max_records: maxRecords,
			});
			oncreated();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="backdrop" onclick={handleBackdrop}>
	<div class="dialog">
		<h2>New Experiment</h2>

		<form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
			<div class="field">
				<label for="exp-name">Name</label>
				<input
					id="exp-name"
					type="text"
					bind:value={name}
					placeholder="e.g. Junction collision baseline"
					required
				/>
			</div>

			<div class="field">
				<label for="exp-dataset">Dataset</label>
				<select id="exp-dataset" bind:value={datasetId} required>
					<option value={null} disabled>Select a dataset</option>
					{#each datasets as ds}
						<option value={ds.id}>{ds.name} ({ds.record_count} records)</option>
					{/each}
				</select>
			</div>

			<div class="field">
				<label for="exp-crash-type">Crash type filter <span class="optional">(optional)</span></label>
				<input
					id="exp-crash-type"
					type="text"
					bind:value={crashTypeFilter}
					placeholder="e.g. REAR END COLLISIONS"
				/>
			</div>

			<div class="field">
				<label for="exp-max">Max records <span class="optional">(cap: 50)</span></label>
				<input
					id="exp-max"
					type="number"
					bind:value={maxRecords}
					min={5}
					max={50}
				/>
			</div>

			<div class="field">
				<span class="field-label">Methods</span>
				<div class="checkboxes">
					<label class="checkbox-label">
						<input type="checkbox" bind:checked={methodPatternBased} />
						<span>pattern_based</span>
					</label>
					<label class="checkbox-label">
						<input type="checkbox" bind:checked={methodFromScratch} />
						<span>from_scratch</span>
					</label>
				</div>
			</div>

			{#if error}
				<div class="error-msg">{error}</div>
			{/if}

			<div class="actions">
				<button type="button" class="btn btn-cancel" onclick={close} disabled={submitting}>
					Cancel
				</button>
				<button
					type="submit"
					class="btn btn-primary"
					disabled={submitting || !name.trim() || datasetId == null}
				>
					{#if submitting}
						<span class="spinner"></span>
						Starting...
					{:else}
						Start Experiment
					{/if}
				</button>
			</div>
		</form>
	</div>
</div>

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 24px;
	}

	.dialog {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 24px;
		width: 100%;
		max-width: 480px;
		max-height: 90vh;
		overflow-y: auto;
	}

	h2 {
		margin: 0 0 20px 0;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--color-text);
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.field > label,
	.field-label {
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--color-muted);
	}

	.optional {
		font-weight: 400;
		font-style: italic;
	}

	input[type='text'],
	input[type='number'],
	select {
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 6px;
		color: var(--color-text);
		font-family: inherit;
		font-size: 0.875rem;
		padding: 8px 10px;
		transition: border-color 0.15s;
	}

	input[type='text']:focus,
	input[type='number']:focus,
	select:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	select {
		cursor: pointer;
		appearance: none;
		background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3' stroke='%238b8d98' fill='none' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
		background-repeat: no-repeat;
		background-position: right 10px center;
		padding-right: 30px;
	}

	.checkboxes {
		display: flex;
		gap: 16px;
	}

	.checkbox-label {
		display: flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
		font-size: 0.82rem;
		color: var(--color-text);
	}

	.checkbox-label input[type='checkbox'] {
		accent-color: var(--color-accent);
		width: 15px;
		height: 15px;
		cursor: pointer;
	}

	.checkbox-label span {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.78rem;
	}

	.error-msg {
		font-size: 0.8rem;
		color: #f87171;
		padding: 8px 10px;
		background: rgba(248, 113, 113, 0.08);
		border: 1px solid rgba(248, 113, 113, 0.2);
		border-radius: 6px;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 4px;
	}

	.btn {
		padding: 8px 16px;
		border-radius: 6px;
		font-size: 0.85rem;
		font-weight: 500;
		border: none;
		cursor: pointer;
		transition: opacity 0.15s, background 0.15s;
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-cancel {
		background: transparent;
		color: var(--color-muted);
		border: 1px solid var(--color-border);
	}

	.btn-cancel:hover:not(:disabled) {
		color: var(--color-text);
		border-color: var(--color-text);
	}

	.btn-primary {
		background: var(--color-accent);
		color: #0f1117;
		font-weight: 600;
	}

	.btn-primary:hover:not(:disabled) {
		opacity: 0.85;
	}

	.spinner {
		display: inline-block;
		width: 12px;
		height: 12px;
		border: 2px solid rgba(15, 17, 23, 0.3);
		border-top-color: #0f1117;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* scrollbar */
	.dialog::-webkit-scrollbar {
		width: 4px;
	}
	.dialog::-webkit-scrollbar-thumb {
		background: var(--color-border);
		border-radius: 4px;
	}
</style>
