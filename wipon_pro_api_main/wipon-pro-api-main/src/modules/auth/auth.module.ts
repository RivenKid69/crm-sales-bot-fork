import { Module } from '@nestjs/common';
import { AuthService } from './domain/auth.service';
import { AuthController } from './presenter/auth.controller';
import { UsersModule } from '../users/users.module';
import { DevicesModule } from '../devices/devices.module';
import { AuthCodesModule } from '../auth-codes/auth-codes.module';
import { SmsModule } from '../sms/sms.module';
import { BillingService } from '../../common/services/billing/billing.service';
import { AccountsModule } from '../accounts/accounts.module';
import { RegionsModule } from '../regions/regions.module';
import { DgdsModule } from '../dgds/dgds.module';
import { UgdsModule } from '../ugds/ugds.module';
import { StoresModule } from '../stores/stores.module';
import { StoreTypesModule } from '../store-types/store-types.module';

@Module({
  providers: [AuthService, BillingService],
  controllers: [AuthController],
  imports: [
    UsersModule,
    DevicesModule,
    AuthCodesModule,
    SmsModule,
    AccountsModule,
    RegionsModule,
    DgdsModule,
    UgdsModule,
    StoresModule,
    StoreTypesModule,
  ],
  exports: [AuthService],
})
export class AuthModule {}
