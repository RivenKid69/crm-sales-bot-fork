import { Process, Processor } from '@nestjs/bull';
import { Job } from 'bull';
import { FindUserByIdUseCase } from '../../../modules/users/domain/use-cases/find-user-by-id.use-case';
import { HttpException } from '@nestjs/common';
import { BillingService } from '../billing/billing.service';
import subscriptionConfig from '../../../config/subscription.config';
import { CountUsersActiveSubscriptionUseCase } from '../../../modules/subscriptions/domain/use-cases/count-users-active-subscription.use-case';
import { ActivateUsersSubscriptionUseCase } from '../../../modules/subscriptions/domain/use-cases/activate-users-subscription.use-case';
import { SubsChargeJobType } from '../../types/subsCharge-job.type';
import { getManager } from 'typeorm';
import { createCustomLogger } from '../../logger/request-logger';

@Processor('billing_pro')
export class SubscriptionChargeConsumer {
  constructor(
    private readonly findUserById: FindUserByIdUseCase,
    private readonly countUsersActiveSubscriptionUseCase: CountUsersActiveSubscriptionUseCase,
    private readonly activateUsersSubscriptionUseCase: ActivateUsersSubscriptionUseCase,
    private readonly billingService: BillingService,
  ) {}
  @Process('billing_pro-job')
  async readOperationJob(job: Job<SubsChargeJobType>) {
    const userId = job.data.userId;
    const logger = createCustomLogger('info', 'subs');
    logger.info(`SubscriptionChargeJob started for user ${userId}`);
    try {
      const user = await this.findUserById.handle(userId);
      if (!user) {
        return logger.log('warn', `User with ID ${userId} not found`);
      }
      const activeSubs = await this.countUsersActiveSubscriptionUseCase.handle(userId);
      if (user && !activeSubs) {
        await getManager().transaction('SERIALIZABLE', async (transactionalEntityManager) => {
          const isUserCharged = await this.billingService.chargeUser(
            transactionalEntityManager,
            user,
            subscriptionConfig.cost,
            {
              subscription_for: {
                date: new Date(),
                timezone: 'UTC',
                timezone_type: 3,
              },
            },
          );
          if (isUserCharged) {
            await this.activateUsersSubscriptionUseCase.handle(
              user,
              subscriptionConfig.lifetime,
              transactionalEntityManager,
            );
          } // if charge
        });
      } // if active
      logger.info({ message: `SubscriptionChargeJob finished for user ${userId}` });
    } catch (e) {
      throw new HttpException(`Subscription charge job failed`, 500);
    }
  }
}
