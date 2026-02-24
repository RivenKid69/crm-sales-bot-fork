import { HttpException, Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SubscriptionRepository } from '../data/subscription.repository';
import { StoreSubscriptionDto } from '../dto/store-subscription.dto';
import { FindUserByPhoneUseCase } from '../../users/domain/use-cases/find-user-by-phone.use-case';
import { addDays, getNowAlmatyTime, greaterThan } from '../../../common/helpers/datetime';
import subscriptionConfig, {
  DESKTOP_TYPE,
  DESKTOP_TYPE_NAME,
  MOBILE_PRICE,
  MOBILE_TYPE,
  subscriptionsTypeName,
  subscriptionsTypePrice,
  TSD_TYPE,
  TSD_TYPE_NAME,
} from '../../../config/subscription.config';
import { ShowActiveSubscriptionDto } from '../dto/show-active-subscription.dto';
import { ShowActiveSubForErpDto } from '../dto/show-active-sub-for-erp.dto';
import { FindUsersStoreByUserIdAndBinUseCase } from '../../stores/domain/use-cases/find-users-store-by-user-id-and-bin.use-case';
import { BuySubscriptionDto } from '../dto/buy-subscription.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { BillingService } from '../../../common/services/billing/billing.service';
import { CountUsersActiveSubscriptionUseCase } from './use-cases/count-users-active-subscription.use-case';
import { EntityManager, getManager, MoreThan } from 'typeorm';
import { ActivateUsersSubscriptionUseCase } from './use-cases/activate-users-subscription.use-case';
import { HttpService } from '@nestjs/axios';
import { FindUsersAllDevicesByAtUseCase } from '../../devices/domain/use-cases/find-users-all-devices-by-at.use-case';
import { DeviceDao } from '../../../common/dao/device.dao';
import { FindUsersAllActiveDevicesUseCase } from '../../devices/domain/use-cases/find-users-all-active-devices.use-case';
import { generateDeviceCode } from '../../../common/helpers/crypto';
import { SubscriptionDao } from '../../../common/dao/subscription.dao';
import { MakeRefundDto } from '../dto/make-refund.dto';
import { getPrefixForDeletedDeviceCode } from '../../../common/utils/common';
const SUBSCRIPTION_REFUND_TYPE = 'sub_refund';

@Injectable()
export class SubscriptionsService {
  constructor(
    @InjectRepository(SubscriptionRepository) private readonly subscriptionRepository: SubscriptionRepository,
    private readonly findUserByPhone: FindUserByPhoneUseCase,
    private readonly findUsersStoreByUserIdAndBin: FindUsersStoreByUserIdAndBinUseCase,
    private readonly billingService: BillingService,
    private readonly countUsersActiveSubs: CountUsersActiveSubscriptionUseCase,
    private readonly activateUsersSubscription: ActivateUsersSubscriptionUseCase,
    private readonly httpService: HttpService,
    private readonly findUsersDevicesByAppType: FindUsersAllDevicesByAtUseCase,
    private readonly findUsersAllActiveDevices: FindUsersAllActiveDevicesUseCase,
  ) {}

  async showActiveSubscriptionByPhone(showActiveSubDto: ShowActiveSubscriptionDto) {
    const user = await this.findUserByPhone.handle(showActiveSubDto.phone_number);
    if (!user) throw new HttpException({ error: 'Пользователь с таким номером не найден' }, 422);
    const sub = await this.subscriptionRepository.findOne({ where: { user_id: user.id, is_active: true } });
    if (!sub) throw new HttpException({ error: 'Отсутствует активная Wipon подписка' }, 404);
    return {
      id: sub.id,
      expires_at: sub.expires_at.toLocaleDateString('ru-RU'),
      is_active: sub.is_active,
    };
  }

  async showActiveSubscriptionForErp(showActiveSubForErp: ShowActiveSubForErpDto) {
    const user = await this.findUserByPhone.handle(showActiveSubForErp.phone_number);
    if (!user) throw new HttpException({ phone_number: ['The selected phone number is invalid.'] }, 422);
    const store = await this.findUsersStoreByUserIdAndBin.handle(user.id, showActiveSubForErp.bin);
    if (!store) throw new HttpException({ store: ['not found'] }, 404);
    const sub = await this.subscriptionRepository.findOne({ where: { user_id: user.id, is_active: true } });
    if (!sub) throw new HttpException({ subscription: ['not found'] }, 404);
    return {
      id: sub.id,
      expires_at: sub.expires_at.toLocaleDateString('ru-RU'),
    };
  }

  async findUsersSubscription(userId: number): Promise<SubscriptionDao | null> {
    const subscription = await this.subscriptionRepository.findUsersSubscription(userId);
    if (!subscription) return null;
    return await this.checkUsersMobileSubscriptionValidity(subscription);
  }

  async checkUsersMobileSubscriptionValidity(subscription: SubscriptionDao): Promise<SubscriptionDao> {
    const now = Date.now();
    const expirationDate = subscription.expires_at.valueOf();
    if (now > expirationDate && subscription.is_active) {
      await this.subscriptionRepository.deactivateSubscription(subscription);
      const deactivated = await this.subscriptionRepository.findOne(subscription.id, { withDeleted: true });
      return deactivated ? deactivated : subscription;
    }
    return subscription;
  }

  async storeSubscription(storeSubscription: StoreSubscriptionDto) {
    const user = await this.findUserByPhone.handle(storeSubscription.phone_number);
    if (!user) {
      throw new NotFoundException(`User with phone number ${storeSubscription.phone_number} not found`);
    }
    const days = storeSubscription.lifetime ?? subscriptionConfig.lifetime;
    const expiresAt = addDays(getNowAlmatyTime(), days);
    const subscription = await this.subscriptionRepository.findOne({ where: { user_id: user.id, is_active: true } });
    if (subscription && greaterThan(subscription.expires_at, expiresAt)) {
      return { status: 'success' };
    }

    await this.subscriptionRepository.update({ user_id: user.id }, { is_active: false });
    await this.subscriptionRepository.softDelete({ user_id: user.id });

    await this.subscriptionRepository.save({
      user_id: user.id,
      is_active: true,
      expires_at: expiresAt,
      type: subscriptionConfig.nurkassa_type,
      created_at: new Date(),
      updated_at: new Date(),
    });

    return { status: 'success' };
  }

  async buySubscription(buySubscriptionDto: BuySubscriptionDto, user: UserDao) {
    if (!buySubscriptionDto.change_subscription_type) {
      const isUserHaveAnyActiveSubscription = await this.checkIsUserHaveAnyActiveSubscription(user);
      if (isUserHaveAnyActiveSubscription) {
        throw new HttpException(
          'Имеется активная подписка, необходимо сменить тариф, либо обратиться в тех. поддержку',
          400,
        );
      }
    }
    buySubscriptionDto.type = Number(buySubscriptionDto.type);
    const priceForSubscription = subscriptionsTypePrice[buySubscriptionDto.type];
    if (!priceForSubscription) throw new HttpException('Not valid price for subscription', 400);

    const ledger = user.ledger;
    if (!ledger) throw new HttpException('User does not have ledger', 400);

    const isUserHasEnoughMoney = await this.billingService.capitalAdequacy(ledger, priceForSubscription);
    if (!isUserHasEnoughMoney) throw new HttpException('Недостаточно денег на счету для покупки', 422);

    if (buySubscriptionDto.type === MOBILE_TYPE) {
      await this.activateMobileSubscription(user, buySubscriptionDto.change_subscription_type);
      return { status: 'success' };
    } else if (buySubscriptionDto.type === DESKTOP_TYPE || buySubscriptionDto.type === TSD_TYPE) {
      return await this.chargeUserAndGenerateQrCodeAndActivateApplication(
        user,
        buySubscriptionDto.type,
        priceForSubscription,
        buySubscriptionDto.change_subscription_type,
      );
    }
  }

  async resetAllActiveSubs(userId: number, transactionalEntityManager: EntityManager) {
    await transactionalEntityManager.update(
      SubscriptionDao,
      { user_id: userId, is_active: true, deleted_at: null, expires_at: MoreThan(new Date()) },
      {
        is_active: false,
        expires_at: new Date(),
        deleted_at: new Date(),
      },
    );

    const date = new Date();
    const yearAgo = new Date(date.setFullYear(date.getFullYear() - 1));

    const devices = await transactionalEntityManager.find(DeviceDao, {
      where: { user_id: userId, updated_at: MoreThan(yearAgo) },
    });

    if (devices && devices.length) {
      devices.forEach((el) => {
        el.user_id = null;
        el.updated_at = new Date();
        el.device_code = getPrefixForDeletedDeviceCode(userId, el.device_code);
      });
    }

    await transactionalEntityManager.save(devices);
  }

  async activateMobileSubscription(user: UserDao, changeSubType: boolean) {
    await getManager().transaction('SERIALIZABLE', async (transactionalEntityManager) => {
      if (changeSubType) await this.resetAllActiveSubs(user.id, transactionalEntityManager);

      const isUserCharged = await this.billingService.chargeUser(transactionalEntityManager, user, MOBILE_PRICE, {
        subscription_for: {
          date: new Date(),
          timezone: 'UTC',
          timezone_type: 3,
        },
      });
      if (isUserCharged) {
        const isActivated = await this.activateUsersSubscription.handle(
          user,
          subscriptionConfig.lifetime,
          transactionalEntityManager,
        );
        if (!isActivated) throw new HttpException('Произошла ошибка во время активации подписки', 500);
      }
    });
  }

  async chargeUserAndGenerateQrCodeAndActivateApplication(
    user: UserDao,
    applicationType: number,
    priceForSubscription: number,
    changeSubType: boolean,
  ) {
    const applicationName = subscriptionsTypeName[applicationType];
    if (!applicationName) throw new HttpException('Неизвестный тип устройства', 400);
    await getManager().transaction('SERIALIZABLE', async (transactionalEntityManager) => {
      if (changeSubType) await this.resetAllActiveSubs(user.id, transactionalEntityManager);
      const isUserCharged = await this.billingService.chargeUser(
        transactionalEntityManager,
        user,
        priceForSubscription,
        {
          subscription_for: {
            date: new Date(),
            timezone: 'UTC',
            timezone_type: 3,
          },
          subscription_name: applicationName,
        },
      );
      if (!isUserCharged) throw new HttpException('Ошибка при попытке списать оплату за подписку', 400);
      const [{ max }] = await transactionalEntityManager.query('SELECT MAX(id) as max from devices');
      const deviceCode = await generateDeviceCode(max, applicationName);
      await transactionalEntityManager.save(DeviceDao, {
        user_id: user.id,
        created_at: new Date(),
        updated_at: new Date(),
        application_type: applicationName,
        device_code: deviceCode,
      });
    });

    return {
      status: 'dataFormed',
    };
  }

  // waitForQrCodeGenerationAndGetUrl(ids: Array<number>) {
  //   return new Promise((resolve, reject) => {
  //     const intervalId = setInterval(async () => {
  //       try {
  //         const checkStatusOfGeneratingQrCodeUrl = `${GENERATE_QR_URL}/generate`;
  //         const checkStatusOfGeneratingQrCodeResponse: any = await this.httpService.axiosRef.get(
  //           checkStatusOfGeneratingQrCodeUrl,
  //           {
  //             headers: {
  //               Cookie: GENERATE_QR_COOKIE,
  //             },
  //             params: {
  //               generateStatus: true,
  //               withoutLoader: true,
  //               quantity: 1,
  //             },
  //           },
  //         );
  //         if (checkStatusOfGeneratingQrCodeResponse.data?.status === 'finished') {
  //           clearInterval(intervalId);
  //           const getGeneratedQrCodeUrl = `${GENERATE_QR_URL}/download-pdf`;
  //           const generatedQrCodeResponse: any = await this.httpService.axiosRef.get(getGeneratedQrCodeUrl, {
  //             headers: {
  //               Cookie: GENERATE_QR_COOKIE,
  //             },
  //             params: {
  //               ids,
  //               withoutLoader: true,
  //               adapter: true,
  //             },
  //           });
  //           if (generatedQrCodeResponse.data?.status) generatedQrCodeResponse.data.status = 'success';
  //           return resolve(generatedQrCodeResponse.data);
  //         }
  //       } catch (e) {
  //         clearInterval(intervalId);
  //         reject(e);
  //       }
  //     }, 5000);
  //   });
  // }

  async checkIsUserHaveAnyActiveSubscription(user: UserDao): Promise<boolean> {
    const mobileActiveSubs = await this.countUsersActiveSubs.handle(user.id);
    if (mobileActiveSubs) return true;
    const desktopAndTsdActiveSubs = await this.findUsersAllActiveDevices.handle(user.id);
    return !!desktopAndTsdActiveSubs;
  }

  async getUsersAllSubscriptions(user: UserDao) {
    const mobileSubs = await this.subscriptionRepository.find({ where: { user_id: user.id }, withDeleted: true });
    const desktopSubs = await this.findUsersDevicesByAppType.handle(user.id, DESKTOP_TYPE_NAME);
    const tsdSubs = await this.findUsersDevicesByAppType.handle(user.id, TSD_TYPE_NAME);
    return {
      mobile: mobileSubs,
      desktop: desktopSubs,
      tsd: tsdSubs,
    };
  }

  async makeRefund(user: UserDao, makeRefundDto: MakeRefundDto) {
    const isUserHaveActiveSub = await this.checkIsUserHaveAnyActiveSubscription(user);
    if (!isUserHaveActiveSub) {
      throw new HttpException('Отсутствует активная подписка', 400);
    }

    const subPrice = subscriptionsTypePrice[makeRefundDto.type];
    const applicationName = subscriptionsTypeName[makeRefundDto.type];

    if (makeRefundDto.type === MOBILE_TYPE) {
      return await this.refundForMobileSubscription(user, makeRefundDto, subPrice, applicationName);
    }
    return await this.refundForTsdOrDesktopSubscription(user, makeRefundDto, subPrice, applicationName);
  }

  async refundForTsdOrDesktopSubscription(user: UserDao, makeRefundDto: MakeRefundDto, subPrice, applicationName) {
    await getManager().transaction(async (transactionalEntityManager) => {
      const subscription = await transactionalEntityManager.findOne(DeviceDao, makeRefundDto.id);
      if (!subscription) throw new HttpException('Отсутствует активная подписка', 400);
      const isSubAvailableForRefund = this.isSubscriptionCreatedDateLowerThanTwoWeeks(subscription.updated_at);
      if (!isSubAvailableForRefund) throw new HttpException('Прошло более 2 недель после покупки тарифа', 400);
      await transactionalEntityManager.update(DeviceDao, subscription.id, {
        user_id: null,
        device_code: getPrefixForDeletedDeviceCode(user.id, subscription.device_code),
      });
      await this.billingService.makeRefund(transactionalEntityManager, user, subPrice, {
        subscription_for: {
          date: new Date(),
          timezone: 'UTC',
          timezone_type: 3,
        },
        subscription_name: applicationName,
        type: 'refund',
      });
    });
    return {
      status: 'success',
    };
  }

  async refundForMobileSubscription(user: UserDao, makeRefundDto: MakeRefundDto, subPrice, applicationName) {
    await getManager().transaction(async (transactionalEntityManager) => {
      const subscription = await transactionalEntityManager.findOne(SubscriptionDao, makeRefundDto.id);
      if (!subscription || !subscription.is_active) throw new HttpException('Отсутствует активная подписка', 400);
      const createdAt = subscription.created_at;
      const isSubAvailableForRefund = this.isSubscriptionCreatedDateLowerThanTwoWeeks(createdAt);
      if (!isSubAvailableForRefund) throw new HttpException('Прошло более 2 недель после покупки тарифа', 400);
      await transactionalEntityManager.update(SubscriptionDao, subscription.id, {
        is_active: false,
        expires_at: new Date(),
        deleted_at: new Date(),
      });
      await this.billingService.makeRefund(transactionalEntityManager, user, subPrice, {
        subscription_for: {
          date: new Date(),
          timezone: 'UTC',
          timezone_type: 3,
        },
        subscription_name: applicationName,
        type: SUBSCRIPTION_REFUND_TYPE,
      });
    });
    return {
      status: 'success',
    };
  }

  isSubscriptionCreatedDateLowerThanTwoWeeks(createdAt: Date): boolean {
    const ONE_DAY_IN_MS = 86400000;
    const twoWeeksAgo = new Date(Date.now() - ONE_DAY_IN_MS * 14);
    return greaterThan(createdAt, twoWeeksAgo);
  }
}
