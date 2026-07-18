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
          <strong>Wav2Lip</strong> (default CPU avatar engine) is released for personal/research/
          non-commercial use only, not commercial use. <strong>SadTalker</strong> (HD tier, added
          task-22) is itself Apache License 2.0 — its own core license changed to commercial-
          permissive in a later release than this product&apos;s specs originally assumed — but it
          depends on GFPGAN (also Apache 2.0) and facexlib model weights for its face-enhancement
          pass; those upstream weight licenses were not independently re-verified here.
          <strong> This flag matters if this product is ever monetized</strong> — re-audit Wav2Lip
          specifically, and the full facexlib/GFPGAN weight chain, before that happens. Fine as-is
          for a free, non-commercial product.
        </p>
        <p style={{ marginTop: "0.5rem" }}>
          <strong>MuseTalk</strong> (enhance pass) — MIT License, free for commercial and
          non-commercial use, though some of its own upstream dependencies (Whisper, DWPose, S3FD)
          carry their own separate licenses.
        </p>
      </Section>

      <Section title="Portrait styling">
        <p>
          <strong>IP-Adapter FaceID</strong> (identity-preserving persona styling, task-22 — the
          local fallback for when Gemini&apos;s image API free tier is unavailable, as it has been
          since July 2026) and the <strong>SDXL base model</strong> it runs on are both
          commercial-usable (Apache License 2.0, and CreativeML Open RAIL++-M respectively — the
          latter permits commercial use with behavioral-use restrictions, not a non-commercial
          clause).
        </p>
        <p style={{ marginTop: "0.5rem" }}>
          <strong>InsightFace</strong> (face-embedding extraction the styler depends on) — its
          Python library is MIT-licensed, but the pretrained <code>buffalo_l</code> model weights
          it downloads are <strong>non-commercial research use only</strong>; a separate commercial
          license would be needed from InsightFace directly before this feature could ever be
          monetized. Joins Wav2Lip in that same &quot;fine free, re-license before monetizing&quot;
          category.
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
          <strong>FLUX.1-schnell</strong> (Apache License 2.0) generates a scene-matched image for
          each scene first, called via its creator&apos;s own public Hugging Face Space rather than
          a paid API — their infrastructure, genuinely free to call. Photographer and source are
          recorded per image and included in every download&apos;s <code>credits.txt</code>; FLUX
          results are labeled AI-generated (FLUX.1-schnell) in the same file. Images falling back
          to a real photo use Pexels or Pixabay, under their respective free API terms. If neither
          produces a usable result, a Gemini-generated image is used instead, also labeled
          AI-generated.
        </p>
      </Section>

      <Section title="Generated footage">
        <p>
          <strong>LTX-2.3</strong> (Lightricks&apos; own community license — free for use below
          US$10M annual revenue, not Apache/MIT/OpenRAIL; this project is non-commercial) animates
          a scene&apos;s image into a short motion clip, called via its creator&apos;s own public
          Hugging Face Space (same pattern as FLUX above) rather than a self-hosted copy. The
          model also generates an audio track, which this site discards — narration and music are
          always produced by the voice and music pipeline, never by the video model. Scenes it can&apos;t reach fall
          back to the home GPU worker, then to a Ken Burns pan/zoom of the still image — each tier
          is recorded per scene in <code>credits.txt</code>.
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
