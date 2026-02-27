<script lang="ts">
	let { src, poster = '' }: { src: string; poster?: string } = $props();
</script>

<div class="video-container">
	<video controls preload="metadata" {poster}>
		<source src={src} type="video/mp4" />
		<p>Your browser does not support HTML5 video.</p>
	</video>
</div>

<style>
	.video-container {
		width: 100%;
		border-radius: 8px;
		overflow: hidden;
		background: #000;
	}

	video {
		width: 100%;
		display: block;
	}
</style>
