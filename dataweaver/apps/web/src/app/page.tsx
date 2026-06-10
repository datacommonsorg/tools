import { PageHome } from '~/components/scopes/page_home';

export const dynamic = 'force-dynamic';

export default function Page() {
  const licenseKey = process.env.TLDRAW_LICENSE_KEY;
  return <PageHome licenseKey={licenseKey} />;
}
