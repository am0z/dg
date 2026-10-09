document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    sources: [],
    messages: [],
    question: "",
    loading: false,
    reindexing: false,
    status: { text: "", error: false },
    failures: [],

    async loadSources() {
      this.sources = await (await fetch("/api/sources")).json();
    },

    async reindex() {
      this.reindexing = true;
      this.status = { text: "", error: false };
      this.failures = [];
      try {
        const res = await fetch("/api/reindex", { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
        this.sources = data.sources;
        const files = Object.keys(data.chunks).length;
        const chunks = Object.values(data.chunks).reduce((a, b) => a + b, 0);
        this.failures = Object.entries(data.errors).map(([source, error]) => ({ source, error }));
        this.status = {
          text: `Indexed ${files} file${files === 1 ? "" : "s"} (${chunks} chunks)` +
            (this.failures.length ? `, ${this.failures.length} failed` : ""),
          error: this.failures.length > 0,
        };
      } catch (err) {
        this.status = { text: `Reindex failed: ${err.message}`, error: true };
      } finally {
        this.reindexing = false;
      }
    },

    async ask() {
      const question = this.question.trim();
      if (!question) return;
      this.question = "";
      this.messages.push({ role: "user", content: question });
      this.messages.push({ role: "assistant", content: "", sources: [] });
      const reply = this.messages[this.messages.length - 1];
      this.loading = true;

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // Response is NDJSON: parse complete lines as they arrive.
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines.filter(Boolean)) {
            const event = JSON.parse(line);
            if (event.sources) reply.sources = event.sources;
            if (event.token) reply.content += event.token;
          }
          this.$nextTick(() => this.$refs.messages.scrollTo(0, 1e9));
        }
      } catch (err) {
        reply.content = `Error: ${err.message}`;
      } finally {
        this.loading = false;
      }
    },
  }));
});
