import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Detector de huella humana',
  description: 'Monitoreo de cuerpos de agua y sus cuencas en Bolivia.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
