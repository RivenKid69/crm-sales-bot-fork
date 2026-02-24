import { BadRequestException, Injectable } from '@nestjs/common';
import { LoginDto } from '../dto/login.dto';
import { FindUserByPhoneUseCase } from '../../users/domain/use-cases/find-user-by-phone.use-case';
import { CreateUserByPhoneUseCase } from '../../users/domain/use-cases/create-user-by-phone-use-case';
import { FindUsersDeviceByApplicationTypeUseCase } from '../../devices/domain/use-cases/find-users-device-by-at';
import { FindUsersAuthCodeUseCase } from '../../auth-codes/domain/use-cases/find-users-auth-code.use-case';
import { addSeconds, diffInSecondsFromNow, gtNow, ltNow } from '../../../common/helpers/datetime';
import { generateToken } from '../../../common/helpers/crypto';
import { SetUsersTokenUseCase } from '../../users/domain/use-cases/set-users-token.use-case';
import { FindNewestUsersAuthCodeUseCase } from '../../auth-codes/domain/use-cases/find-newest-users-auth-code.use-case';
import authConfig from '../../../config/auth.config';
import { DeleteUsersAllAuthCodesUseCase } from '../../auth-codes/domain/use-cases/delete-users-all-auth-codes.use-case';
import { CreateUsersAuthCodeUseCase } from '../../auth-codes/domain/use-cases/create-users-auth-code.use-case';
import { SmsService } from '../../sms/sms.service';
import { FindUserByTokenUseCase } from '../../users/domain/use-cases/find-user-by-token.use-case';
import { BillingService } from '../../../common/services/billing/billing.service';
import testConfig from '../../../config/test.config';
import { StoresService } from '../../stores/domain/stores.service';
import { FindUsersStoreUseCase } from '../../stores/domain/use-cases/find-users-store.use-case';
import { PostOrUpdateStoreDto } from '../../stores/dto/post-or-update-store.dto';
import { FindRegionByNameUseCase } from '../../regions/domain/use-cases/find-region-by-name.use-case';
import { FindUgdByDgdIdUseCase } from '../../ugds/domain/use-cases/find-ugd-by-dgd-id.use-case';
import { FindStoresTypeByNameUseCase } from '../../store-types/domain/use-cases/find-stores-type-by-name.use-case';
import { UsersService } from '../../users/domain/users.service';
import { FindDgdByIdUseCase } from '../../dgds/domain/use-cases/find-dgd-by-id.use-case';
import { UserDao } from '../../../common/dao/user.dao';

@Injectable()
export class AuthService {
  constructor(
    private readonly findUserByPhone: FindUserByPhoneUseCase,
    private readonly findUserByToken: FindUserByTokenUseCase,
    private readonly createUserByPhone: CreateUserByPhoneUseCase,
    private readonly findUsersDeviceByApplicationType: FindUsersDeviceByApplicationTypeUseCase,
    private readonly findUsersAuthCode: FindUsersAuthCodeUseCase,
    private readonly deleteUsersAllAuthCodes: DeleteUsersAllAuthCodesUseCase,
    private readonly setUsersToken: SetUsersTokenUseCase,
    private readonly findNewestUsersAuthCode: FindNewestUsersAuthCodeUseCase,
    private readonly createUsersAuthCode: CreateUsersAuthCodeUseCase,
    private readonly findRegionByName: FindRegionByNameUseCase,
    private readonly smsService: SmsService,
    private readonly billingService: BillingService,
    private readonly findUsersStore: FindUsersStoreUseCase,
    private readonly storeService: StoresService,
    private readonly findDgdByIdUseCase: FindDgdByIdUseCase,
    private readonly findUgdByDgdIdUseCase: FindUgdByDgdIdUseCase,
    private readonly findStoresTypeByNameUseCase: FindStoresTypeByNameUseCase,
    private readonly usersService: UsersService,
  ) {}

  async login(loginDto: LoginDto) {
    let user: null | undefined | UserDao;
    let apiToken: null | string;
    user = await this.findUserByPhone.handle(loginDto.phone_number);
    if (!user) {
      user = await this.createUserByPhone.handle(loginDto.phone_number);
      await this.billingService.createAccounts(user);
    }

    const authCode = loginDto.auth_code;
    const applicationType = loginDto.application_type;
    const deviceInfo: { has_device: boolean; device_code?: string } = {
      has_device: false,
    };

    if (user.phone_number == testConfig.user.phone_number || user.phone_number == testConfig._user.phone_number) {
      if (!authCode) {
        return {
          resend_cooldown: authConfig.authCodes.testAuthCodeEmpty,
          status: 'success',
        };
      } // if empty authCode

      if (authCode == testConfig.auth_code) {
        if (user.phone_number == testConfig.user.phone_number) {
          apiToken = await this.updateUserAndStore(user);
        } else {
          apiToken = await this.updateUser(user);
        } // if test user
        return {
          status: 'success',
          api_token: apiToken,
          ...deviceInfo,
        };
      } else {
        throw new BadRequestException({
          status: 'error',
          error: 'Wrong authentication code',
        });
      } // if authCode
    }

    if (applicationType) {
      const device = await this.findUsersDeviceByApplicationType.handle(user.id, applicationType);

      if (device) {
        deviceInfo.has_device = true;
        deviceInfo.device_code = device.device_code;
      }
    }

    if (authCode) {
      const userAuthCode = await this.findUsersAuthCode.handle(user.id, authCode);

      if (!userAuthCode) {
        throw new BadRequestException({
          status: 'error',
          error: 'Wrong authentication code',
        });
      }

      if (ltNow(userAuthCode.expires_at)) {
        throw new BadRequestException({
          status: 'error',
          error: 'Authentication code is expired',
        });
      }

      const token = await generateToken();

      await this.deleteUsersAllAuthCodes.handle(user.id);

      // $ip = $request->ip();
      // if ($ip && array_key_exists($ip, config('ip-third_party'))) {
      //   $thirdPartyApiToken = ThirdPartyApiToken::firstOrNew([
      //     'api_token' => $token
      // ]);
      //   $thirdPartyApiToken->user_id = $user->id;
      //   $thirdPartyApiToken->third_party = config('ip-third_party')[$ip];
      //   $thirdPartyApiToken->save();
      // } else {
      //   $user->api_token = $token;
      //   $user->save();
      // }

      await this.setUsersToken.handle(user.id, token);
      await this.billingService.createAccounts(user);
      return {
        api_token: token,
        status: 'success',
        ...deviceInfo,
      };
    }

    let userAuthCode = await this.findNewestUsersAuthCode.handle(user.id);

    if (userAuthCode) {
      if (gtNow(addSeconds(userAuthCode.created_at, authConfig.authCodes.sendCooldown))) {
        throw new BadRequestException({
          status: 'pending',
          error: "Can't send authentication code",
          resend_cooldown: authConfig.authCodes.sendCooldown - diffInSecondsFromNow(userAuthCode.created_at),
        });
      }
    }

    await this.deleteUsersAllAuthCodes.handle(user.id);
    userAuthCode = await this.createUsersAuthCode.handle(user.id);

    await this.smsService.sendAuthCode(user.phone_number, userAuthCode.code);

    return {
      status: 'success',
      resend_cooldown: authConfig.authCodes.sendCooldown,
    };
  }

  async updateUserAndStore(user: UserDao) {
    const token = await generateToken();

    await this.setUsersToken.handle(user.id, token);
    // const userData = new UserDao({ ...user, ...testConfig.user });
    // await this.usersService.updateUserData(userData);
    //
    // const storeDto = new PostOrUpdateStoreDto();
    //
    // if (await this.findUsersStore.handle(user.id)) {
    //   await this.storeService.saveOrUpdateStore(user.id, { ...storeDto, ...testConfig.store });
    //   return true;
    // }
    //
    // const region = await this.findRegionByName.handle('Нур-Султан (Астана)');
    // const business_store_type = await this.findStoresTypeByNameUseCase.handle('Розница');
    // const business = await this.findDgdByIdUseCase.handle('0301');
    // const business_ugd = await this.findUgdByDgdIdUseCase.handle('0301');
    //
    // if (region) {
    //   storeDto.region_id = region.id;
    // }
    //
    // if (business_store_type) {
    //   storeDto.buisness_store_type_id = business_store_type.id;
    // }
    //
    // if (business) {
    //   storeDto.buisness_dgd_id = String(business.id);
    // }
    //
    // if (business_ugd) {
    //   storeDto.buisness_ugd_id = String(business_ugd.id);
    // }
    //
    // await this.storeService.saveOrUpdateStore(user.id, { ...storeDto, ...testConfig.store });
    return token;
  }

  async updateUser(user: UserDao) {
    const token = await generateToken();
    await this.setUsersToken.handle(user.id, token);
    // const userData = new UserDao({ ...user, ...testConfig.user });
    // await this.usersService.updateUserData(userData);
    return token;
  }
}
