import type { A2UIComponent } from "../types";

interface A2UIDisplayProps {
  components: A2UIComponent[];
}

function ExecutiveSummary({ props }: { props: Record<string, unknown> }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-5">
      {props.title ? (
        <h3 className="text-lg font-semibold text-cyan-400 mb-2">{String(props.title)}</h3>
      ) : null}
      {props.summary ? <p className="text-gray-200 leading-relaxed">{String(props.summary)}</p> : null}
    </div>
  );
}

function StatCard({ props }: { props: Record<string, unknown> }) {
  const items = Array.isArray(props.items) ? props.items : [];
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4">
      {props.title ? (
        <h4 className="text-sm font-medium text-gray-400 mb-3">{String(props.title)}</h4>
      ) : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map((item: Record<string, unknown>, i: number) => (
          <div key={i} className="text-center">
            <div className="text-xl font-bold text-teal-400">{String(item.value ?? "")}</div>
            <div className="text-xs text-gray-400 mt-1">{String(item.label ?? "")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StepCard({ props }: { props: Record<string, unknown> }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4 flex gap-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-cyan-600/30 border border-cyan-500/40 flex items-center justify-center text-sm font-bold text-cyan-400">
        {props.step_number != null ? String(props.step_number) : "#"}
      </div>
      <div className="flex-1">
        {props.title ? (
          <h4 className="text-sm font-semibold text-gray-200 mb-1">{String(props.title)}</h4>
        ) : null}
        {props.description ? (
          <p className="text-sm text-gray-400">{String(props.description)}</p>
        ) : null}
      </div>
    </div>
  );
}

function CodeBlock({ props }: { props: Record<string, unknown> }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg overflow-hidden">
      {props.language ? (
        <div className="px-3 py-1.5 border-b border-white/10 text-xs text-gray-500 font-mono">
          {String(props.language)}
        </div>
      ) : null}
      <pre className="bg-black/40 p-4 overflow-x-auto">
        <code className="text-green-400 font-mono text-sm">{String(props.code ?? props.content ?? "")}</code>
      </pre>
    </div>
  );
}

function ChecklistItem({ props }: { props: Record<string, unknown> }) {
  const checked = Boolean(props.checked);
  return (
    <div className="flex items-start gap-2 py-1">
      <div
        className={`mt-0.5 w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${
          checked
            ? "bg-cyan-600/40 border-cyan-500/60 text-cyan-400"
            : "border-white/20 text-transparent"
        }`}
      >
        {checked && (
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>
      <span className={`text-sm ${checked ? "text-gray-400 line-through" : "text-gray-200"}`}>
        {String(props.label ?? props.text ?? "")}
      </span>
    </div>
  );
}

function CalloutCard({ props }: { props: Record<string, unknown> }) {
  const variant = String(props.variant ?? props.type ?? "info");
  const variantStyles: Record<string, string> = {
    info: "border-cyan-500/30 bg-cyan-500/5",
    warning: "border-amber-500/30 bg-amber-500/5",
    error: "border-red-500/30 bg-red-500/5",
    success: "border-green-500/30 bg-green-500/5",
  };
  const variantTextStyles: Record<string, string> = {
    info: "text-cyan-400",
    warning: "text-amber-400",
    error: "text-red-400",
    success: "text-green-400",
  };

  const borderBg = variantStyles[variant] ?? variantStyles.info;
  const textColor = variantTextStyles[variant] ?? variantTextStyles.info;

  return (
    <div className={`backdrop-blur-sm border rounded-lg p-4 ${borderBg}`}>
      {props.title ? (
        <h4 className={`text-sm font-semibold mb-1 ${textColor}`}>{String(props.title)}</h4>
      ) : null}
      {props.message ? <p className="text-sm text-gray-300">{String(props.message)}</p> : null}
    </div>
  );
}

function UnknownComponent({ component }: { component: A2UIComponent }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-lg p-4">
      <div className="text-xs text-gray-500 font-mono mb-2">{component.type}</div>
      <pre className="text-xs text-gray-400 font-mono overflow-x-auto">
        {JSON.stringify(component.props, null, 2)}
      </pre>
    </div>
  );
}

const COMPONENT_MAP: Record<string, React.ComponentType<{ props: Record<string, unknown> }>> = {
  "a2ui.ExecutiveSummary": ExecutiveSummary,
  "a2ui.StatCard": StatCard,
  "a2ui.StepCard": StepCard,
  "a2ui.CodeBlock": CodeBlock,
  "a2ui.ChecklistItem": ChecklistItem,
  "a2ui.CalloutCard": CalloutCard,
};

export function A2UIDisplay({ components }: A2UIDisplayProps) {
  if (!components.length) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3">
      {components.map((component) => {
        const Renderer = COMPONENT_MAP[component.type];
        if (Renderer) {
          return <Renderer key={component.id} props={component.props} />;
        }
        return <UnknownComponent key={component.id} component={component} />;
      })}
    </div>
  );
}
