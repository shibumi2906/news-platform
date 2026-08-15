import { publicThemeManifest } from "@/lib/theme";

export function GET() {
  return Response.json(publicThemeManifest, { headers: { "Cache-Control": "public, max-age=3600" } });
}
