'use client';

import { useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import CustomerDetailContent from './CustomerDetailContent';
import { useSidebarData } from '@/app/home/components/home-sidebar/SidebarDataContext';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';
import { backendClient } from '@/app/infra/http';

export default function CustomersPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const detailId = searchParams.get('id');
  const { customers } = useSidebarData();
  const [keyword, setKeyword] = useState('');
  const [exporting, setExporting] = useState(false);

  const filteredCustomers = useMemo(() => {
    const normalized = keyword.trim().toLowerCase();
    if (!normalized) return customers;
    return customers.filter((item) => {
      const name = item.name?.toLowerCase() || '';
      const desc = item.description?.toLowerCase() || '';
      return name.includes(normalized) || desc.includes(normalized);
    });
  }, [customers, keyword]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await backendClient.downloadFile('/api/v1/customers/export');
      const contentDisposition = response.headers['content-disposition'];
      let filename = `customers-${Date.now()}.xlsx`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      // Keep UI simple; log details for debugging.
      console.error('Failed to export customers:', error);
    } finally {
      setExporting(false);
    }
  };

  if (detailId) {
    return <CustomerDetailContent id={detailId} />;
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl font-semibold">{t('customers.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('customers.description')}</p>
        </div>
        <Button onClick={handleExport} disabled={exporting} variant="outline">
          <Download className="mr-2 h-4 w-4" />
          {exporting ? t('customers.exporting') : t('customers.export')}
        </Button>
      </div>

      <div className="mb-4">
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t('customers.searchPlaceholder')}
        />
      </div>

      {filteredCustomers.length === 0 ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <p>{t('customers.empty')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredCustomers.map((customer) => (
            <button
              key={customer.id}
              type="button"
              className="block w-full rounded-lg border p-4 text-left transition-colors hover:bg-muted/30"
              onClick={() =>
                router.push(`/home/customers?id=${encodeURIComponent(customer.id)}`)
              }
            >
              <div className="mb-1 flex items-center justify-between gap-3">
                <div className="font-medium">{customer.name}</div>
                <Badge variant="secondary">{t('customers.viewDetail')}</Badge>
              </div>
              <div className="text-sm text-muted-foreground">{customer.description || '-'}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
