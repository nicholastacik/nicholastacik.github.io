import { z } from "zod";

export interface Shape {
  orig: string;
  dest?: string;
  brush: string;
}

export interface AuthoredNode {
  san: string;
  comment?: string;
  nag?: string;
  shapes?: Shape[];
  alts?: AuthoredNode[][];
}

export interface Study {
  id: string;
  name: string;
  eco?: string;
  side: "white" | "black" | "both";
  intro: string;
  line: AuthoredNode[];
}

const shapeSchema: z.ZodType<Shape> = z
  .object({
    orig: z.string(),
    dest: z.string().optional(),
    brush: z.string(),
  })
  .strict();

const nodeSchema: z.ZodType<AuthoredNode> = z.lazy(() =>
  z
    .object({
      san: z.string().min(2),
      comment: z.string().optional(),
      nag: z.string().optional(),
      shapes: z.array(shapeSchema).optional(),
      alts: z.array(z.array(nodeSchema)).optional(),
    })
    .strict(),
);

export const studySchema: z.ZodType<Study> = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+$/),
    name: z.string().min(1),
    eco: z.string().optional(),
    side: z.enum(["white", "black", "both"]),
    intro: z.string().min(1),
    line: z.array(nodeSchema).min(1),
  })
  .strict();

export function parseStudy(data: unknown): Study {
  return studySchema.parse(data);
}

// Eagerly import every study JSON at build time. Vite returns the parsed
// object as each module's default export. Validated here so a malformed
// study fails fast (in tests and at build), never silently in the browser.
const modules = import.meta.glob<Study>("./studies/*.json", {
  eager: true,
  import: "default",
});

export function loadStudies(): Study[] {
  return Object.values(modules)
    .map((m) => studySchema.parse(m))
    .sort((a, b) => a.name.localeCompare(b.name));
}
