// Shape of shared/meta.json produced by scripts/generate_pages.py (render_meta).
export interface SourceMeta {
  name: string;
  hue: number;
}

export interface ImportanceMeta {
  label: string;
  description: string;
}

export interface SharedMeta {
  schema_version: number;
  site_url: string;
  site_name: string;
  data_url: string;
  placeholder: {
    formula: string;
    saturation: number;
    lightness: number;
  };
  sources: SourceMeta[];
  importance: Record<string, ImportanceMeta>;
  model_types: Record<string, string>;
}
