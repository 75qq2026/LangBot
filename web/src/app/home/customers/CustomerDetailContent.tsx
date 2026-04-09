'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowLeft, Building2, MessageSquare, Phone, User } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { httpClient } from '@/app/infra/http/HttpClient';
import { useSidebarData } from '@/app/home/components/home-sidebar/SidebarDataContext';
import { Customer, CustomerConversation } from '@/app/infra/entities/api';

function getRoleVariant(role: string) {
  return role === 'assistant' ? 'secondary' : 'default';
}

function getStatusVariant(status: string) {
  if (status === 'complete') {
    return 'default';
  }
  if (status === 'partial') {
    return 'secondary';
  }
  return 'outline';
}

function extractDisplayText(conversation: CustomerConversation) {
  if (conversation.message_text) {
    return conversation.message_text;
  }

  try {
    const payload = JSON.parse(conversation.message_content);
    if (!Array.isArray(payload)) {
      return conversation.message_content;
    }

    return payload
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return '';
        }

        if (item.type === 'Plain') {
          return item.text || '';
        }
        if (item.type === 'Image') {
          return '[Image]';
        }
        if (item.type === 'File') {
          return `[File: ${item.name || 'File'}]`;
        }
        if (item.type === 'Voice') {
          return '[Voice]';
        }
        return item.type ? `[${item.type}]` : '';
      })
      .join('');
  } catch {
    return conversation.message_content;
  }
}

export default function CustomerDetailContent({ id }: { id: string }) {
  const router = useRouter();
  const { t } = useTranslation();
  const { customers, setDetailEntityName } = useSidebarData();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [conversations, setConversations] = useState<CustomerConversation[]>(
    [],
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const sidebarCustomer = customers.find((item) => item.id === id);
    setDetailEntityName(sidebarCustomer?.name ?? id);
    return () => setDetailEntityName(null);
  }, [customers, id, setDetailEntityName]);

  useEffect(() => {
    let active = true;

    async function loadData() {
      setLoading(true);
      try {
        const [detailResp, conversationResp] = await Promise.all([
          httpClient.getCustomer(id),
          httpClient.getCustomerConversations(id),
        ]);

        if (!active) {
          return;
        }

        setCustomer(detailResp.customer);
        setConversations(conversationResp.conversations);
      } catch (error) {
        console.error('Failed to load customer detail:', error);
        toast.error(t('customers.loadDetailError'));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadData();

    return () => {
      active = false;
    };
  }, [id, t]);

  const tags = useMemo(() => customer?.tags ?? [], [customer]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        {t('common.loading')}
      </div>
    );
  }

  if (!customer) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
        <p>{t('customers.notFound')}</p>
        <Button
          variant="outline"
          onClick={() => router.push('/home/customers')}
        >
          <ArrowLeft className="mr-2 size-4" />
          {t('customers.backToList')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto pb-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">
              {customer.customer_name || customer.user_name || customer.user_id}
            </h1>
            <Badge variant={getStatusVariant(customer.profile_status)}>
              {t(`customers.status.${customer.profile_status}`)}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {t('customers.lastContactAt')}:{' '}
            {customer.last_contact_at
              ? new Date(customer.last_contact_at).toLocaleString()
              : '-'}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => router.push('/home/customers')}
        >
          <ArrowLeft className="mr-2 size-4" />
          {t('customers.backToList')}
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{t('customers.profileTitle')}</CardTitle>
            <CardDescription>
              {t('customers.profileDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3 text-sm">
              <div className="flex items-start gap-3">
                <User className="mt-0.5 size-4 text-muted-foreground" />
                <div>
                  <div className="text-muted-foreground">
                    {t('customers.fields.name')}
                  </div>
                  <div>{customer.customer_name || '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Phone className="mt-0.5 size-4 text-muted-foreground" />
                <div>
                  <div className="text-muted-foreground">
                    {t('customers.fields.phone')}
                  </div>
                  <div>{customer.phone || '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Building2 className="mt-0.5 size-4 text-muted-foreground" />
                <div>
                  <div className="text-muted-foreground">
                    {t('customers.fields.company')}
                  </div>
                  <div>{customer.company || '-'}</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <MessageSquare className="mt-0.5 size-4 text-muted-foreground" />
                <div>
                  <div className="text-muted-foreground">
                    {t('customers.fields.intent')}
                  </div>
                  <div>{customer.intent || '-'}</div>
                </div>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('customers.fields.requirementSummary')}
              </div>
              <div className="rounded-md bg-muted p-3 text-sm">
                {customer.requirement_summary || '-'}
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('customers.fields.notes')}
              </div>
              <div className="rounded-md bg-muted p-3 text-sm">
                {customer.notes || '-'}
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium">
                {t('customers.fields.tags')}
              </div>
              <div className="flex flex-wrap gap-2">
                {tags.length > 0 ? (
                  tags.map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">-</span>
                )}
              </div>
            </div>

            <Separator />

            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-muted-foreground">
                  {t('customers.fields.bot')}
                </div>
                <div>{customer.bot_name || '-'}</div>
              </div>
              <div>
                <div className="text-muted-foreground">
                  {t('customers.fields.pipeline')}
                </div>
                <div>{customer.pipeline_name || '-'}</div>
              </div>
              <div>
                <div className="text-muted-foreground">
                  {t('customers.fields.conversationCount')}
                </div>
                <div>{customer.conversation_count ?? 0}</div>
              </div>
              <div>
                <div className="text-muted-foreground">
                  {t('customers.fields.user')}
                </div>
                <div>{customer.user_name || customer.user_id || '-'}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('customers.timelineTitle')}</CardTitle>
            <CardDescription>
              {t('customers.timelineDescription')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {conversations.length === 0 ? (
              <div className="py-10 text-center text-sm text-muted-foreground">
                {t('customers.emptyTimeline')}
              </div>
            ) : (
              <div className="space-y-4">
                {conversations.map((conversation, index) => (
                  <div key={conversation.id} className="relative pl-6">
                    {index < conversations.length - 1 && (
                      <div className="absolute left-[9px] top-8 h-[calc(100%+0.75rem)] w-px bg-border" />
                    )}
                    <div className="absolute left-0 top-1.5 size-[18px] rounded-full border-2 border-background bg-primary" />
                    <div className="rounded-xl border p-4">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge variant={getRoleVariant(conversation.role)}>
                          {t(`customers.roles.${conversation.role}`)}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {new Date(conversation.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div className="whitespace-pre-wrap break-words text-sm leading-6">
                        {extractDisplayText(conversation)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
