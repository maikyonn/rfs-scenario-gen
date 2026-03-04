<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { marked } from 'marked';
	import ToolCallCard from '$lib/components/ToolCallCard.svelte';
	import ScenarioPanel from '$lib/components/ScenarioPanel.svelte';

	// ── Types ─────────────────────────────────────────────────────────────────

	type ToolCall = {
		id: string;           // tool_start event may fire before tool_end; match by name+order
		name: string;
		input: unknown;
		output?: unknown;
		status: 'running' | 'done' | 'error';
		subStatus?: string;   // live progress text from tool_progress SSE events
	};

	type Message =
		| { role: 'user'; content: string }
		| { role: 'assistant'; content: string; toolCalls: ToolCall[] };

	// ── State ─────────────────────────────────────────────────────────────────

	let sessionId = $state<string | null>(null);
	let messages = $state<Message[]>([]);
	let inputText = $state('');
	let isStreaming = $state(false);
	let currentVideo = $state<{ url: string; thumbnail: string | null } | null>(null);
	let currentConfig = $state<Record<string, unknown> | null>(null);
	let validated = $state(false);
	let xoscUrl = $state<string | null>(null);

	let messagesEl = $state<HTMLDivElement | null>(null);
	let textareaEl = $state<HTMLTextAreaElement | null>(null);

	const hasUserMessage = $derived(messages.some(m => m.role === 'user'));

	const EXAMPLES = [
		'Drunk driver runs a red light and gets T-boned by a crossing SUV at 45mph',
		'Road-rage motorcycle at 70mph rear-ends a suddenly braking sedan',
		'Wrong-way pickup truck head-ons a delivery van at 3am',
		'Cyclist doored by a parked taxi and thrown into oncoming traffic',
		'Distracted pedestrian steps into traffic at dusk, sedan swerves into an SUV',
	];

	import { PUBLIC_API_BASE } from '$env/static/public';
	const API = PUBLIC_API_BASE || '';

	// ── On mount: create session ──────────────────────────────────────────────

	onMount(async () => {
		try {
			const res = await fetch(`${API}/api/chat`, { method: 'POST' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			sessionId = data.session_id;
		} catch (e) {
			messages.push({
				role: 'assistant',
				content: `Failed to connect to the API: ${e}`,
				toolCalls: [],
			});
			return;
		}

		messages.push({
			role: 'assistant',
			content: 'Hello! Describe a crash scenario and I\'ll generate, validate, and render it for you. Try one of the examples below, or type your own.',
			toolCalls: [],
		});
	});

	// ── Send message ──────────────────────────────────────────────────────────

	async function sendMessage() {
		const text = inputText.trim();
		if (!text || isStreaming || !sessionId) return;

		inputText = '';
		isStreaming = true;
		needsTextSeparator = false;

		// Clear right panel so stale data doesn't linger while new scenario generates
		currentVideo = null;
		currentConfig = null;
		validated = false;
		xoscUrl = null;

		// Remove the template greeting before the first user message
		if (messages.length === 1 && messages[0].role === 'assistant') {
			messages.splice(0, 1);
		}

		messages.push({ role: 'user', content: text });
		// Push the assistant message and immediately get the proxied reference back.
		// In Svelte 5 $state, mutations must go through the reactive proxy — reading
		// the element back via messages[idx] returns the proxied object so that
		// property assignments (content +=, toolCalls.push) trigger DOM updates.
		messages.push({ role: 'assistant', content: '', toolCalls: [] });
		const assistantMsg = messages[messages.length - 1] as Message & { role: 'assistant' };

		await tick();
		scrollToBottom();

		try {
			const res = await fetch(`${API}/api/chat/${sessionId}/message`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ content: text }),
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);

			const reader = res.body!.getReader();
			const decoder = new TextDecoder();
			let buffer = '';

			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				buffer += decoder.decode(value, { stream: true });

				const lines = buffer.split('\n');
				buffer = lines.pop() ?? '';

				for (const line of lines) {
					if (!line.startsWith('data: ')) continue;
					const raw = line.slice(6).trim();
					if (!raw) continue;

					let event: Record<string, unknown>;
					try {
						event = JSON.parse(raw);
					} catch {
						continue;
					}

					handleSseEvent(assistantMsg, event);
					await tick();
					scrollToBottom();
				}
			}
		} catch (e) {
			assistantMsg.content += `\n\nConnection error: ${e}`;
		} finally {
			isStreaming = false;
		}
	}

	let needsTextSeparator = false;

	function handleSseEvent(msg: Message & { role: 'assistant' }, event: Record<string, unknown>) {
		const type = event.type as string;

		if (type === 'text_delta') {
			const delta = (event.delta as string) ?? '';
			if (needsTextSeparator && msg.content && !msg.content.endsWith('\n') && !delta.startsWith('\n')) {
				msg.content += '\n\n';
			}
			msg.content += delta;
			needsTextSeparator = false;
		}

		if (type === 'tool_start') {
			const tc: ToolCall = {
				id: `${event.name}-${msg.toolCalls.length}`,
				name: event.name as string,
				input: event.input,
				status: 'running',
			};
			msg.toolCalls.push(tc);
		}

		if (type === 'tool_progress') {
			// Find the last running tool call with matching name and update its sub-status
			const tc = [...msg.toolCalls].reverse().find(t => t.name === (event.name as string) && t.status === 'running');
			if (tc) tc.subStatus = event.message as string;
		}

		if (type === 'tool_end') {
			const name = event.name as string;
			const output = event.output;
			needsTextSeparator = true;
			// Find the last running tool call with this name
			const tc = [...msg.toolCalls].reverse().find(t => t.name === name && t.status === 'running');
			if (tc) {
				tc.output = output;
				tc.status = 'done';

				// Update scenario panel state from tool outputs
				if (name === 'render_scenario') {
					const o = output as Record<string, unknown>;
					if (o.mp4_url) {
						currentVideo = {
							url: o.mp4_url as string,
							thumbnail: (o.thumbnail_url as string | null) ?? null,
						};
					}
				}
				if (name === 'validate_collision') {
					const o = output as Record<string, unknown>;
					validated = Boolean(o.collision_detected);
				}
				if (name === 'build_scenario') {
					const o = output as Record<string, unknown>;
					if (o.xosc_url) xoscUrl = o.xosc_url as string;
				}
				if (name === 'generate_crash_config' || name === 'modify_config') {
					const raw = typeof output === 'string' ? output : JSON.stringify(output);
					if (!raw.startsWith('ERROR:')) {
						try {
							currentConfig = JSON.parse(typeof output === 'string' ? output : JSON.stringify(output));
						} catch { /* ignore */ }
					}
				}
			}
		}

		if (type === 'error') {
			msg.content += `\n\nError: ${event.message}`;
		}
	}

	function scrollToBottom() {
		if (messagesEl) {
			messagesEl.scrollTop = messagesEl.scrollHeight;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}
</script>

<svelte:head>
	<title>Generate Scenario — RFS</title>
</svelte:head>

<div class="layout">
	<!-- ── Left: Chat ──────────────────────────────────────────────────────── -->
	<div class="chat-col">
		<div class="messages" bind:this={messagesEl}>
			{#each messages as msg}
				{#if msg.role === 'user'}
					<div class="msg msg-user">
						<div class="bubble bubble-user">{msg.content}</div>
					</div>
				{:else}
					<div class="msg msg-assistant">
						{#if msg.toolCalls.length > 0}
							<div class="tool-calls">
								{#each msg.toolCalls as tc (tc.id)}
									<ToolCallCard
										name={tc.name}
										input={tc.input}
										output={tc.output}
										status={tc.status}
										subStatus={tc.subStatus}
									/>
								{/each}
							</div>
						{/if}
						{#if msg.content}
							<div class="bubble bubble-assistant md">{@html marked(msg.content)}</div>
						{/if}
					</div>
				{/if}
			{/each}

			{#if isStreaming}
				<div class="typing-indicator">
					<span></span><span></span><span></span>
				</div>
			{/if}
		</div>

		<!-- Input area -->
		<div class="input-area">
			{#if !hasUserMessage}
				<div class="examples">
					{#each EXAMPLES as ex}
						<button
							class="chip"
							onclick={() => { inputText = ex; textareaEl?.focus(); }}
							disabled={isStreaming}
						>{ex}</button>
					{/each}
				</div>
			{/if}
			<div class="input-row">
				<textarea
					bind:this={textareaEl}
					bind:value={inputText}
					placeholder="Describe a crash scenario…"
					rows="2"
					disabled={isStreaming}
					onkeydown={handleKeydown}
				></textarea>
				<button
					class="btn-send"
					onclick={sendMessage}
					disabled={!inputText.trim() || isStreaming || !sessionId}
					aria-label="Send"
				>
					{#if isStreaming}
						<span class="spinner"></span>
					{:else}
						<svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
							<path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
						</svg>
					{/if}
				</button>
			</div>
		</div>
	</div>

	<!-- ── Right: Scenario Panel ───────────────────────────────────────────── -->
	<div class="panel-col">
		<div class="panel-header">
			<h2>Scenario</h2>
		</div>
		<ScenarioPanel
			videoUrl={currentVideo?.url ?? null}
			thumbnailUrl={currentVideo?.thumbnail ?? null}
			config={currentConfig}
			{validated}
			{xoscUrl}
		/>
	</div>
</div>

<style>
	.layout {
		display: grid;
		grid-template-columns: 1fr 360px;
		gap: 20px;
		height: calc(100vh - 97px); /* viewport minus header + padding */
	}

	/* ── Chat column ── */
	.chat-col {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-height: 0;
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 4px 2px;
		min-height: 0;
	}

	.msg {
		display: flex;
	}

	.msg-user {
		justify-content: flex-end;
	}

	.msg-assistant {
		flex-direction: column;
		gap: 6px;
	}

	.bubble {
		padding: 10px 14px;
		border-radius: 10px;
		font-size: 0.9rem;
		line-height: 1.55;
		white-space: pre-wrap;
		word-break: break-word;
		max-width: 85%;
	}

	.bubble-user {
		background: var(--color-accent-dim);
		border: 1px solid rgba(96, 165, 250, 0.2);
		color: var(--color-text);
		border-bottom-right-radius: 3px;
	}

	.bubble-assistant {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text);
		border-bottom-left-radius: 3px;
		max-width: 100%;
	}

	/* Markdown rendering inside assistant bubbles */
	:global(.bubble-assistant.md > *:first-child) { margin-top: 0; }
	:global(.bubble-assistant.md > *:last-child)  { margin-bottom: 0; }
	:global(.bubble-assistant.md p)   { margin: 0.45em 0; line-height: 1.6; }
	:global(.bubble-assistant.md h1),
	:global(.bubble-assistant.md h2),
	:global(.bubble-assistant.md h3) {
		font-weight: 600;
		margin: 0.8em 0 0.3em;
		color: var(--color-text);
	}
	:global(.bubble-assistant.md h3) { font-size: 0.95rem; }
	:global(.bubble-assistant.md h2) { font-size: 1rem; }
	:global(.bubble-assistant.md ul),
	:global(.bubble-assistant.md ol) {
		margin: 0.4em 0;
		padding-left: 1.4em;
	}
	:global(.bubble-assistant.md li) { margin: 0.2em 0; }
	:global(.bubble-assistant.md code) {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.82em;
		background: rgba(96, 165, 250, 0.1);
		border: 1px solid rgba(96, 165, 250, 0.2);
		border-radius: 3px;
		padding: 0.1em 0.35em;
	}
	:global(.bubble-assistant.md pre) {
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 6px;
		padding: 10px 12px;
		overflow-x: auto;
		margin: 0.5em 0;
	}
	:global(.bubble-assistant.md pre code) {
		background: none;
		border: none;
		padding: 0;
		font-size: 0.8rem;
	}
	:global(.bubble-assistant.md table) {
		border-collapse: collapse;
		width: 100%;
		margin: 0.5em 0;
		font-size: 0.85rem;
	}
	:global(.bubble-assistant.md th),
	:global(.bubble-assistant.md td) {
		border: 1px solid var(--color-border);
		padding: 5px 10px;
		text-align: left;
	}
	:global(.bubble-assistant.md th) {
		background: rgba(96, 165, 250, 0.08);
		font-weight: 600;
	}
	:global(.bubble-assistant.md tr:nth-child(even) td) {
		background: rgba(255,255,255,0.02);
	}
	:global(.bubble-assistant.md strong) { font-weight: 600; }
	:global(.bubble-assistant.md em)     { font-style: italic; color: var(--color-muted); }
	:global(.bubble-assistant.md hr) {
		border: none;
		border-top: 1px solid var(--color-border);
		margin: 0.7em 0;
	}
	:global(.bubble-assistant.md a) {
		color: var(--color-accent);
		text-decoration: none;
	}
	:global(.bubble-assistant.md a:hover) { text-decoration: underline; }

	.tool-calls {
		display: flex;
		flex-direction: column;
		gap: 2px;
		max-width: 100%;
	}

	/* typing indicator */
	.typing-indicator {
		display: flex;
		gap: 4px;
		padding: 10px 0 2px 4px;
	}

	.typing-indicator span {
		display: block;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--color-muted);
		animation: bounce 1.2s infinite;
	}

	.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
	.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

	@keyframes bounce {
		0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
		40% { transform: translateY(-5px); opacity: 1; }
	}

	/* ── Input area ── */
	.input-area {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.examples {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.chip {
		font-size: 0.75rem;
		padding: 4px 10px;
		border-radius: 20px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		cursor: pointer;
		transition: color 0.15s, border-color 0.15s;
		white-space: nowrap;
	}

	.chip:hover:not(:disabled) {
		color: var(--color-accent);
		border-color: rgba(96, 165, 250, 0.4);
	}

	.chip:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.input-row {
		display: flex;
		gap: 8px;
		align-items: flex-end;
	}

	textarea {
		flex: 1;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-text);
		font-family: inherit;
		font-size: 0.9rem;
		line-height: 1.5;
		padding: 10px 12px;
		resize: none;
		transition: border-color 0.15s;
	}

	textarea:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	textarea:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-send {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		background: var(--color-accent);
		color: #0f1117;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: opacity 0.15s;
		flex-shrink: 0;
	}

	.btn-send:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.btn-send:not(:disabled):hover {
		opacity: 0.85;
	}

	.spinner {
		display: inline-block;
		width: 14px;
		height: 14px;
		border: 2px solid rgba(15, 17, 23, 0.3);
		border-top-color: #0f1117;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* ── Scenario panel column ── */
	.panel-col {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-height: 0;
		overflow-y: auto;
	}

	.panel-header h2 {
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-size: 0.75rem;
	}

	/* scrollbar */
	.messages::-webkit-scrollbar,
	.panel-col::-webkit-scrollbar {
		width: 4px;
	}
	.messages::-webkit-scrollbar-thumb,
	.panel-col::-webkit-scrollbar-thumb {
		background: var(--color-border);
		border-radius: 4px;
	}
</style>
