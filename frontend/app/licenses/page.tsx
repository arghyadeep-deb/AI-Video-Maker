// specs/04-tasks/task-21-launch.md's "Licenses page" checklist item.
// Static, no auth required.
import Link from "next/link";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: "2rem" }}>
      <h2 style={{ fontSize: "1.05rem", fontWeight: 600 }}>{title}</h2>
      <div style={{ color: "var(--text-dim)", marginTop: "0.5rem", lineHeight: 1.6 }}>{children}</div>
    </section>
  );
}

export default function LicensesPage() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "4rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Licenses & third-party terms</h1>
      <p style={{ color: "var(--text-dim)", marginTop: "1rem", lineHeight: 1.6 }}>
        This product is built entirely on free and open-source components. Everything below is
        used within its own license terms.
      </p>

      <Section title="Fonts">
        <p>
          Noto Sans and Noto Sans Devanagari — SIL Open Font License 1.1. Used for burned-in
          subtitles in both languages.
        </p>
      </Section>

      <Section title="Talking-head models">
        <p>
          <strong>Wav2Lip</strong> (default CPU avatar engine) and <strong>SadTalker</strong> (HD
          tier) are both released for personal/research/non-commercial use only, not commercial
          use. <strong>This flag matters if this product is ever monetized</strong> — re-license or
          replace both before that happens. Fine as-is for a free, non-commercial product.
        </p>
        <p style={{ marginTop: "0.5rem" }}>
          <strong>MuseTalk</strong> (enhance pass) — MIT License, free for commercial and
          non-commercial use, though some of its own upstream dependencies (Whisper, DWPose, S3FD)
          carry their own separate licenses.
        </p>
      </Section>

      <Section title="Voice models">
        <p>
          <strong>OpenVoice V2</strong> (tone-color conversion, the default personal-voice engine)
          — MIT License, free for commercial and non-commercial use.
        </p>
        <p style={{ marginTop: "0.5rem" }}>
          <strong>VoxCPM</strong> (HD voice / designed personas) — Apache License 2.0.
        </p>
        <p style={{ marginTop: "0.5rem" }}>
          <strong>edge-tts</strong> (base narration voice + word timings) wraps Microsoft Edge&apos;s
          Read Aloud service through an unofficial, reverse-engineered interface — not an
          officially published or supported API. It has been reliable in practice, but Microsoft
          could change or remove it at any time without notice.
        </p>
      </Section>

      <Section title="Background music">
        <p>
          All bundled tracks are by Jason Shaw (audionautix.com), mirrored on Wikimedia Commons,
          licensed CC BY 3.0 — attribution &quot;music by audionautix.com&quot; required and
          included in every render&apos;s credits. Full per-track list:{" "}
          <a
            href="https://commons.wikimedia.org/wiki/Category:Audionautix"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent)" }}
          >
            see backend/assets/music/LICENSES.md
          </a>
          .
        </p>
      </Section>

      <Section title="Stock images">
        <p>
          Pexels and Pixabay, used under their respective free API terms. Photographer and source
          are recorded per image and included in every download&apos;s <code>credits.txt</code>.
          Images with no usable stock result fall back to Gemini-generated images, labeled as
          AI-generated in the same credits file.
        </p>
      </Section>

      <Section title="Hosting">
        <p>
          Frontend hosted on Vercel&apos;s Hobby (free) plan, whose terms restrict it to
          non-commercial use — consistent with this being a private, non-commercial project.
        </p>
      </Section>

      <p style={{ marginTop: "2rem" }}>
        <Link href="/responsible-use" style={{ color: "var(--accent)" }}>Responsible use</Link>
        {" · "}
        <Link href="/privacy" style={{ color: "var(--accent)" }}>Privacy & data</Link>
      </p>
    </main>
  );
}
