'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Download, RefreshCw, Search } from 'lucide-react';
import { toast } from 'sonner';

import CustomerDetailContent from './CustomerDetailContent';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { backendClient, httpClient } from '@/app/infra/http';
import { Customer } from '@/app/infra/entities/api';
import { useSidebarData } from '@/app/home/components/home-sidebar/SidebarDataContext';

function getStatusVariant(status: string) {
  if (status === 'complete') {
    return 'default';
  }
  if (status === 'partial') {
    return 'secondary';
  }
  return 'outline';
}

export default function CustomersPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const detailId = searchParams.get('id');
  const { refreshCustomers, setDetailEntityName } = useSidebarData();

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const totalCustomers = useMemo(() => customers.length, [customers]);

  useEffect(() => {
    if (detailId) {
      return;
    }
    setDetailEntityName(null);
  }, [detailId, setDetailEntityName]);

  useEffect(() => {
    if (detailId) {
      return;
    }

    let active = true;

    async function loadCustomers() {
      setLoading(true);
      try {
        const response = await httpClient.getCustomers({
          keyword: keyword.trim() || undefined,
          limit: 100,
          offset: 0,
        });
        if (!active) {
          return;
        }
        setCustomers(response.customers);
      } catch (error) {
        console.error('Failed to load customers:', error);
        toast.error(t('customers.loadListError'));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadCustomers();

    return () => {
      active = false;
    };
  }, [detailId, keyword, t]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (keyword.trim()) {
        params.set('keyword', keyword.trim());
      }

      const response = await backendClient.downloadFile(
        `/api/v1/customers/export${params.toString() ? `?${params.toString()}` : ''}`,
      );

      const contentDisposition = response.headers['content-disposition'];
      let filename = `customers-${Date.now()}.xlsx`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
        if (match) {
          filename = match[1];
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
      console.error('Failed to export customers:', error);
      toast.error(t('customers.exportError'));
    } finally {
      setExporting(false);
    }
  };

  const handleRefresh = async () => {
    await refreshCustomers();
    setKeyword((value) => value);
  };

  if (detailId) {
    return <CustomerDetailContent id={detailId} />;
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto pb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t('customers.title')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('customers.description')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={loading}>
            <RefreshCw className="mr-2 size-4" />
            {t('customers.refresh')}
          </Button>
          <Button onClick={handleExport} disabled={exporting}>
            <Download className="mr-2 size-4" />
            {exporting ? t('customers.exporting') : t('customers.export')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('customers.listTitle')}</CardTitle>
          <CardDescription>{t('customers.listDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative max-w-md flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder={t('customers.searchPlaceholder')}
                className="pl-9"
              />
            </div>
            <div className="text-sm text-muted-foreground">
              {t('customers.totalCount', { count: totalCustomers })}
            </div>
          </div>

          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('customers.fields.name')}</TableHead>
                  <TableHead>{t('customers.fields.phone')}</TableHead>
                  <TableHead>{t('customers.fields.company')}</TableHead>
                  <TableHead>{t('customers.fields.intent')}</TableHead>
                  <TableHead>{t('customers.fields.status')}</TableHead>
                  <TableHead>{t('customers.fields.lastContactAt')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-24 text-center text-muted-foreground"
                    >
                      {t('common.loading')}
                    </TableCell>
                  </TableRow>
                ) : customers.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={6}
                      className="h-24 text-center text-muted-foreground"
                    >
                      {t('customers.emptyList')}
                    </TableCell>
                  </TableRow>
                ) : (
                  customers.map((customer) => (
                    <TableRow
                      key={customer.id}
                      className="cursor-pointer"
                      onClick={() =>
                        router.push(
                          `/home/customers?id=${encodeURIComponent(customer.id)}`,
                        )
                      }
                    >
                      <TableCell className="font-medium">
                        {customer.customer_name ||
                          customer.user_name ||
                          customer.user_id}
                      </TableCell>
                      <TableCell>{customer.phone || '-'}</TableCell>
                      <TableCell>{customer.company || '-'}</TableCell>
                      <TableCell className="max-w-[280px] truncate">
                        {customer.intent || customer.requirement_summary || '-'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={getStatusVariant(customer.profile_status)}
                        >
                          {t(`customers.status.${customer.profile_status}`)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {customer.last_contact_at
                          ? new Date(customer.last_contact_at).toLocaleString()
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
