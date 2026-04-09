'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  Building2,
  Download,
  Mail,
  MessageSquare,
  Phone,
  Search,
  UserRound,
} from 'lucide-react';

import { httpClient } from '@/app/infra/http/HttpClient';
import type {
  Customer,
  CustomerConversation,
} from '@/app/infra/entities/api';
import { useSidebarData } from '@/app/home/components/home-sidebar/SidebarDataContext';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

function formatDateTime(value?: string | null) {
  if (!value) {
    return '--';
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function getDisplayName(customer?: Customer | null) {
  if (!customer) {
    return '-';
  }
  return (
    customer.display_name ||
    customer.name ||
    customer.user_name ||
    customer.user_id ||
    '-'
  );
}

export default function CustomersPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedCustomerId = searchParams.get('id');
  const { setDetailEntityName } = useSidebarData();

  const [keywordInput, setKeywordInput] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [customerDetail, setCustomerDetail] = useState<Customer | null>(null);
  const [conversations, setConversations] = useState<CustomerConversation[]>([]);

  const fetchCustomers = useCallback(async () => {
    setLoadingList(true);
    try {
      const result = await httpClient.getCustomers({
        keyword: appliedKeyword || undefined,
        limit: 100,
        offset: 0,
      });
      setCustomers(result.customers);
      setTotal(result.total);

      if (result.customers.length === 0) {
        setCustomerDetail(null);
        setConversations([]);
        if (selectedCustomerId) {
          router.replace('/home/customers');
        }
        return;
      }

      const currentExists = result.customers.some(
        (customer) => customer.id === selectedCustomerId,
      );
      if (!selectedCustomerId || !currentExists) {
        router.replace(
          `/home/customers?id=${encodeURIComponent(result.customers[0].id)}`,
        );
      }
    } catch (error) {
      console.error('Failed to fetch customers:', error);
      toast.error(t('customers.loadListError'));
    } finally {
      setLoadingList(false);
    }
  }, [appliedKeyword, router, selectedCustomerId, t]);

  const fetchCustomerDetail = useCallback(async () => {
    if (!selectedCustomerId) {
      setCustomerDetail(null);
      setConversations([]);
      return;
    }

    setLoadingDetail(true);
    try {
      const [customerResult, conversationResult] = await Promise.all([
        httpClient.getCustomer(selectedCustomerId),
        httpClient.getCustomerConversations(selectedCustomerId, {
          limit: 500,
          offset: 0,
        }),
      ]);
      setCustomerDetail(customerResult.customer);
      setConversations(conversationResult.conversations);
    } catch (error) {
      console.error('Failed to fetch customer detail:', error);
      toast.error(t('customers.loadDetailError'));
      setCustomerDetail(null);
      setConversations([]);
    } finally {
      setLoadingDetail(false);
    }
  }, [selectedCustomerId, t]);

  useEffect(() => {
    fetchCustomers();
  }, [fetchCustomers]);

  useEffect(() => {
    fetchCustomerDetail();
  }, [fetchCustomerDetail]);

  useEffect(() => {
    if (selectedCustomerId && customerDetail) {
      setDetailEntityName(getDisplayName(customerDetail));
      return () => setDetailEntityName(null);
    }
    setDetailEntityName(t('customers.title'));
    return () => setDetailEntityName(null);
  }, [customerDetail, selectedCustomerId, setDetailEntityName, t]);

  const selectedSummary = useMemo(() => {
    if (!customerDetail) {
      return t('customers.emptyDetailHint');
    }
    return customerDetail.latest_summary || t('customers.noSummary');
  }, [customerDetail, t]);

  const handleSearch = useCallback(() => {
    setAppliedKeyword(keywordInput.trim());
  }, [keywordInput]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const response = await httpClient.exportCustomers({
        keyword: appliedKeyword || undefined,
      });
      const blob = new Blob([response.data], {
        type:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      const disposition = response.headers['content-disposition'] as
        | string
        | undefined;
      const match = disposition?.match(/filename="([^"]+)"/);
      anchor.href = url;
      anchor.download = match?.[1] || 'customers.xlsx';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export customers:', error);
      toast.error(t('customers.exportError'));
    } finally {
      setExporting(false);
    }
  }, [appliedKeyword, t]);

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">{t('customers.title')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('customers.description')}
          </p>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="flex gap-2">
            <Input
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch();
                }
              }}
              placeholder={t('customers.searchPlaceholder')}
              className="w-full sm:w-72"
            />
            <Button variant="outline" onClick={handleSearch}>
              <Search className="mr-2 h-4 w-4" />
              {t('common.search')}
            </Button>
          </div>
          <Button onClick={handleExport} disabled={exporting}>
            <Download className="mr-2 h-4 w-4" />
            {exporting ? t('customers.exporting') : t('customers.export')}
          </Button>
        </div>
      </div>

      <div className="grid flex-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>{t('customers.listTitle')}</CardTitle>
            <CardDescription>
              {t('customers.listDescription', { count: total })}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <ScrollArea className="h-[calc(100vh-18rem)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('customers.columns.name')}</TableHead>
                    <TableHead>{t('customers.columns.phone')}</TableHead>
                    <TableHead>{t('customers.columns.lastContact')}</TableHead>
                    <TableHead className="text-right">
                      {t('customers.columns.conversations')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingList ? (
                    <TableRow>
                      <TableCell colSpan={4} className="h-24 text-center">
                        {t('common.loading')}
                      </TableCell>
                    </TableRow>
                  ) : customers.length > 0 ? (
                    customers.map((customer) => (
                      <TableRow
                        key={customer.id}
                        className={cn(
                          'cursor-pointer',
                          selectedCustomerId === customer.id &&
                            'bg-muted/60 hover:bg-muted/60',
                        )}
                        onClick={() =>
                          router.push(
                            `/home/customers?id=${encodeURIComponent(
                              customer.id,
                            )}`,
                          )
                        }
                      >
                        <TableCell className="max-w-[180px]">
                          <div className="truncate font-medium">
                            {getDisplayName(customer)}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">
                            {customer.company || customer.user_name || '--'}
                          </div>
                        </TableCell>
                        <TableCell>{customer.phone || '--'}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDateTime(customer.last_contact_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          {customer.conversation_count}
                        </TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={4} className="h-24 text-center">
                        {t('customers.emptyList')}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>

        <div className="flex min-h-0 flex-col gap-4 lg:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle>{t('customers.detailTitle')}</CardTitle>
              <CardDescription>{selectedSummary}</CardDescription>
            </CardHeader>
            <CardContent>
              {loadingDetail ? (
                <div className="py-8 text-sm text-muted-foreground">
                  {t('common.loading')}
                </div>
              ) : customerDetail ? (
                <div className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <UserRound className="h-4 w-4" />
                        {t('customers.fields.name')}
                      </div>
                      <div className="font-medium">{customerDetail.name || '--'}</div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Phone className="h-4 w-4" />
                        {t('customers.fields.phone')}
                      </div>
                      <div className="font-medium">
                        {customerDetail.phone || '--'}
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Mail className="h-4 w-4" />
                        {t('customers.fields.email')}
                      </div>
                      <div className="font-medium">
                        {customerDetail.email || '--'}
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Building2 className="h-4 w-4" />
                        {t('customers.fields.company')}
                      </div>
                      <div className="font-medium">
                        {customerDetail.company || '--'}
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <MessageSquare className="h-4 w-4" />
                        {t('customers.fields.conversationCount')}
                      </div>
                      <div className="font-medium">
                        {customerDetail.conversation_count}
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">
                        {t('customers.fields.lastContact')}
                      </div>
                      <div className="font-medium">
                        {formatDateTime(customerDetail.last_contact_at)}
                      </div>
                    </div>
                  </div>

                  <Separator />

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="space-y-2">
                      <h3 className="font-medium">
                        {t('customers.fields.requirements')}
                      </h3>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {customerDetail.requirements || '--'}
                      </p>
                    </div>
                    <div className="space-y-2">
                      <h3 className="font-medium">
                        {t('customers.fields.notes')}
                      </h3>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {customerDetail.notes || '--'}
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h3 className="font-medium">{t('customers.fields.tags')}</h3>
                    <div className="flex flex-wrap gap-2">
                      {customerDetail.tags && customerDetail.tags.length > 0 ? (
                        customerDetail.tags.map((tag) => (
                          <Badge key={tag} variant="secondary">
                            {tag}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">--</span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-8 text-sm text-muted-foreground">
                  {t('customers.emptyDetailHint')}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 flex-1">
            <CardHeader>
              <CardTitle>{t('customers.timelineTitle')}</CardTitle>
              <CardDescription>{t('customers.timelineDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0">
              <ScrollArea className="h-[calc(100vh-30rem)] pr-4">
                {loadingDetail ? (
                  <div className="py-8 text-sm text-muted-foreground">
                    {t('common.loading')}
                  </div>
                ) : conversations.length > 0 ? (
                  <div className="space-y-4">
                    {conversations.map((conversation) => {
                      const isUser = conversation.role === 'user';
                      return (
                        <div
                          key={conversation.id}
                          className={cn(
                            'rounded-lg border p-4',
                            isUser ? 'border-blue-200 bg-blue-50/50' : 'bg-card',
                          )}
                        >
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <Badge variant={isUser ? 'default' : 'secondary'}>
                              {isUser
                                ? t('customers.timeline.user')
                                : t('customers.timeline.assistant')}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {formatDateTime(conversation.created_at)}
                            </span>
                            {conversation.pipeline_name && (
                              <span className="text-xs text-muted-foreground">
                                {conversation.pipeline_name}
                              </span>
                            )}
                          </div>
                          <p className="whitespace-pre-wrap text-sm leading-6">
                            {conversation.content_text || '--'}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-8 text-sm text-muted-foreground">
                    {t('customers.emptyTimeline')}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
