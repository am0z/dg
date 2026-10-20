const THREAD_KEY = "dg.threadId";

// crypto.randomUUID only exists on https/localhost; fall back elsewhere (e.g. LAN IP).
function newThreadId() {
  return crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// localStorage can throw (private mode, blocked storage); the chat still works without it.
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch {} },
};

document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    sources: [],
    messages: [],
    preferences: {},
    threadId: "",
    question: "",
    loading: false,
    reindexing: false,
    status: { text: "", error: false },
    failures: [],

    async init() {
      this.threadId = storage.get(THREAD_KEY) ?? this.startThread();
      await Promise.all([this.loadSources(), this.loadConversation()]);
    },

    async loadSources() {
      this.sources = await (await fetch("/api/sources")).json();
    },

    async loadConversation() {
      const res = await fetch(`/api/conversations/${this.threadId}`);
      if (!res.ok) return;
      const data = await res.json();
      this.messages = data.messages;
      this.preferences = data.preferences;
      this.scrollToBottom();
    },

    startThread() {
      const id = newThreadId();
      storage.set(THREAD_KEY, id);
      return id;
    },

    newChat() {
      this.threadId = this.startThread();
      this.messages = [];
      this.preferences = {};
    },

    scrollToBottom() {
      this.$nextTick(() => this.$refs.messages.scrollTo(0, 1e9));
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
      this.messages.push({ role: "user", content: question, sources: [] });
      this.messages.push({ role: "assistant", content: "", sources: [] });
      const reply = this.messages[this.messages.length - 1];
      this.loading = true;

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, thread_id: this.threadId }),
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
            if (event.preferences) this.preferences = event.preferences;
            if (event.sources) reply.sources = event.sources;
            if (event.token) reply.content += event.token;
          }
          this.scrollToBottom();
        }
      } catch (err) {
        reply.content = `Error: ${err.message}`;
      } finally {
        this.loading = false;
      }
    },
  }));
});
