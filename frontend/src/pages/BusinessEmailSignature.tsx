import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import DOMPurify from "dompurify";
import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import TextStyle from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
import { apiClient } from "../api/client";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { Toggle } from "../components/Toggle";
import { Card, Button, cn } from "../design-system";

/**
 * Business Branding: Email Signature. The signature belongs to the
 * Business (BrandEmailSignature, 1:1 with CompanyProfile) - not to any
 * OutreachPlaybook/PromptVersion/OutreachDraft. Editing it here never
 * creates a new Playbook version; it is mutable-in-place settings, exactly
 * like Workspace Settings and the CompanyProfile editor. Outreach draft
 * generation reads whatever is saved here at render time and freezes the
 * exact HTML into that draft's ai_generated_content.assembled.signature_html
 * for permanent explainability - editing the signature later never rewrites
 * history for drafts already generated.
 *
 * M8.7 Phase E3: the surrounding page chrome (card, toolbar, buttons,
 * labels) is restyled to the dark design-system tokens like every other
 * migrated page. The editor surface and preview pane deliberately stay
 * light/white, not dark - a signature is composed and read against a
 * white email background in every real mail client, so rendering it in a
 * dark box here would misrepresent what recipients actually see. This is
 * the one legitimate exception to "no light surfaces" in this migration,
 * for the same reason a photo editor's canvas doesn't recolor the photo.
 */

const SIGNATURE_COLORS = ["#0f172a", "#334155", "#1d4ed8", "#b91c1c", "#047857"];

interface SignatureData {
  signature_html: string | null;
  is_active: boolean;
}

function ToolbarButton({
  onClick,
  active,
  children,
  title,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "rounded px-2 py-1 text-xs font-medium",
        active ? "bg-accent-primary text-white" : "text-slate-700 hover:bg-slate-200"
      )}
    >
      {children}
    </button>
  );
}

function Toolbar({ editor }: { editor: Editor | null }) {
  if (!editor) return null;

  const setLink = () => {
    const previous = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("Link URL", previous ?? "https://");
    if (url === null) return;
    if (url === "") {
      editor.chain().focus().unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1 rounded-t-md border border-b-0 border-slate-300 bg-slate-100 p-1.5">
      <ToolbarButton title="Bold" active={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
        <strong>B</strong>
      </ToolbarButton>
      <ToolbarButton title="Italic" active={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <em>I</em>
      </ToolbarButton>
      <ToolbarButton title="Underline" active={editor.isActive("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()}>
        <span className="underline">U</span>
      </ToolbarButton>
      <span className="mx-1 h-4 w-px bg-slate-300" />
      <ToolbarButton title="Bullet list" active={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        • List
      </ToolbarButton>
      <ToolbarButton title="Numbered list" active={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        1. List
      </ToolbarButton>
      <span className="mx-1 h-4 w-px bg-slate-300" />
      <ToolbarButton title="Link" active={editor.isActive("link")} onClick={setLink}>
        Link
      </ToolbarButton>
      <ToolbarButton title="Remove formatting" onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}>
        Clear
      </ToolbarButton>
      <span className="mx-1 h-4 w-px bg-slate-300" />
      {SIGNATURE_COLORS.map((color) => (
        <button
          key={color}
          type="button"
          title={color}
          onClick={() => editor.chain().focus().setColor(color).run()}
          className="h-5 w-5 rounded-full border border-slate-300"
          style={{ backgroundColor: color }}
        />
      ))}
    </div>
  );
}

/**
 * BusinessEmailSignature — M8.7 Phase E3 (Settings zone). Migrated in
 * place per Design Bible Section 9.2: identical fetch/save calls, only
 * the page chrome moves onto design-system tokens/primitives (see the
 * module docstring above for why the editor/preview surfaces stay light).
 */
export default function BusinessEmailSignature() {
  const { companyId } = useParams();
  const [isActive, setIsActive] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState(false);
  const savedMessageTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  // TipTap's internal ProseMirror state changes don't trigger a React
  // re-render on their own - onUpdate mirrors the current HTML into plain
  // React state so the sanitized preview below actually stays in sync as
  // the user types.
  const [previewHtml, setPreviewHtml] = useState("");

  const editor = useEditor({
    extensions: [StarterKit, Underline, TextStyle, Color, Link.configure({ openOnClick: false })],
    content: "",
    onUpdate: ({ editor: e }: { editor: Editor }) => setPreviewHtml(e.getHTML()),
  });

  // Shared fetch, same "silent refresh after save" pattern used by
  // CompanyICP.tsx and Prospects.tsx: the initial mount shows the
  // full-page loading state; the post-save refresh does not, so the
  // editor never unmounts/remounts and scroll position is preserved.
  const fetchData = (showLoadingScreen: boolean) => {
    if (showLoadingScreen) setIsLoading(true);
    return apiClient
      .get<SignatureData>(`/branding/company-profiles/${companyId}/email-signature`)
      .then((res) => {
        setIsActive(res.data.is_active);
        const html = res.data.signature_html ?? "";
        if (editor && !editor.isDestroyed) {
          editor.commands.setContent(html, false);
        }
        setPreviewHtml(html);
        if (showLoadingScreen) setIsLoading(false);
      });
  };

  const load = () => {
    void fetchData(true);
  };
  const refreshAfterSave = () => fetchData(false);

  // Only re-run on companyId/editor-readiness changes - not on every
  // editor content change, which would fight the user's own typing.
  useEffect(load, [companyId, editor]);

  useEffect(() => {
    return () => {
      if (savedMessageTimeout.current) clearTimeout(savedMessageTimeout.current);
    };
  }, []);

  const showSavedMessage = () => {
    setSavedMessage(true);
    if (savedMessageTimeout.current) clearTimeout(savedMessageTimeout.current);
    savedMessageTimeout.current = setTimeout(() => setSavedMessage(false), 3000);
  };

  const handleSave = async () => {
    if (!editor) return;
    setIsSaving(true);
    setError(null);
    setSavedMessage(false);
    try {
      await apiClient.put(`/branding/company-profiles/${companyId}/email-signature`, {
        signature_html: editor.getHTML(),
        is_active: isActive,
      });
      await refreshAfterSave();
      showSavedMessage();
    } catch {
      setError("Could not save the email signature.");
    } finally {
      setIsSaving(false);
    }
  };

  const sanitizedPreview = useMemo(() => DOMPurify.sanitize(previewHtml), [previewHtml]);

  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumbs items={[{ label: "Businesses", to: "/businesses" }, { label: "Email Signature" }]} />

      <h1 className="mb-1 text-h1 font-semibold text-slate-100">Business Email Signature</h1>
      <p className="mb-6 text-body text-slate-400">
        This signature belongs to the business, not to any Outreach Playbook. Every generated Outreach email
        draft appends whatever is saved here at generation time - editing it later never rewrites the history of
        drafts already sent.
      </p>

      {error && <p className="mb-4 text-sm text-status-danger">{error}</p>}

      <Card className="mb-6">
        <div className="mb-4 flex items-center justify-between">
          <label className="text-sm font-medium text-slate-300">Active</label>
          <Toggle checked={isActive} onChange={setIsActive} />
        </div>

        <Toolbar editor={editor} />
        <EditorContent
          editor={editor}
          className="min-h-[160px] rounded-b-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus-within:border-slate-500 [&_.ProseMirror]:min-h-[140px] [&_.ProseMirror]:outline-none"
        />

        <div className="mt-6 flex items-center justify-end gap-3">
          {savedMessage && <span className="text-sm font-medium text-status-success">Changes saved</span>}
          <Button onClick={handleSave} isLoading={isSaving}>
            Save signature
          </Button>
        </div>
      </Card>

      <Card>
        <p className="mb-3 text-sm font-medium text-slate-200">Preview</p>
        <div className="rounded-md bg-slate-50 p-4 text-sm text-slate-700" dangerouslySetInnerHTML={{ __html: sanitizedPreview }} />
      </Card>
    </div>
  );
}
