import { CacheModule, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import databaseConfig from 'src/config/database.config';
import { AuthModule } from 'src/modules/auth/auth.module';
import { UsersModule } from './modules/users/users.module';
import { ChecksModule } from './modules/checks/checks.module';
import { SubscriptionsModule } from './modules/subscriptions/subscriptions.module';
import { AuthCodesModule } from './modules/auth-codes/auth-codes.module';
import { DevicesModule } from './modules/devices/devices.module';
import { SmsModule } from './modules/sms/sms.module';
import { RegionsModule } from './modules/regions/regions.module';
import { DgdsModule } from './modules/dgds/dgds.module';
import { FeedbacksModule } from './modules/feedbacks/feedbacks.module';
import { UgdsModule } from './modules/ugds/ugds.module';
import { NotificationsModule } from './modules/notifications/notifications.module';
import { ReportsModule } from './modules/reports/reports.module';
import { LicensesModule } from './modules/licenses/licenses.module';
import { AccountsModule } from './modules/accounts/accounts.module';
import { TransactionsModule } from './modules/transactions/transactions.module';
import { LedgersModule } from './modules/ledgers/ledgers.module';
import { CashboxesModule } from './modules/cashboxes/cashboxes.module';
import { BillingsModule } from './modules/billings/billings.module';
import { AcceptLanguageResolver, HeaderResolver, I18nJsonParser, I18nModule, QueryResolver } from 'nestjs-i18n';
import * as path from 'path';
import { AppController } from './app.controller';
import { StoresModule } from './modules/stores/stores.module';
import { StoreTypesModule } from './modules/store-types/store-types.module';
import { BullModule } from '@nestjs/bull';
import { VersionModule } from './modules/version/version.module';
import { PdfModule } from './modules/pdf/pdf.module';
import redisConfig from './config/redis.config';
import { ScheduleModule } from '@nestjs/schedule';
import * as redisStore from 'cache-manager-redis-store';
import { TasksModule } from './common/services/tasks/tasks.module';
import { UgdLicensesModule } from './modules/ugd-licenses/ugd-licenses.module';
// import ormConfig from '../ormconfig';

const entitiesPath = path.resolve('dist', 'common', 'dao', '*.dao{.ts,.js}');

@Module({
  controllers: [AppController],
  imports: [
    TypeOrmModule.forRoot({
      name: 'default',
      type: 'postgres',
      host: databaseConfig.host,
      port: databaseConfig.port,
      username: databaseConfig.username,
      password: databaseConfig.password,
      database: databaseConfig.database,
      entities: [entitiesPath],
      autoLoadEntities: false,
      synchronize: false,
      schema: 'public',
    }),
    // TypeOrmModule.forRoot({
    //   ...ormConfig,
    //   name: 'second-db',
    // }),
    ScheduleModule.forRoot(),
    I18nModule.forRoot({
      fallbackLanguage: 'ru',
      fallbacks: {
        'en-*': 'en',
        'ru-*': 'ru',
        'kk-*': 'kk',
      },
      parser: I18nJsonParser,
      parserOptions: {
        path: path.join(__dirname, '/i18n/'),
      },
      resolvers: [
        { use: QueryResolver, options: ['lang', 'locale', 'l'] },
        new HeaderResolver(['lang']),
        AcceptLanguageResolver,
      ],
    }),
    BullModule.forRoot({
      redis: {
        host: redisConfig.host,
        port: Number(redisConfig.port),
      },
    }),
    CacheModule.register({
      store: redisStore,
      host: redisConfig.host,
      port: Number(redisConfig.port),
    }),
    TasksModule,
    AuthModule,
    UsersModule,
    ChecksModule,
    SubscriptionsModule,
    StoresModule,
    AuthCodesModule,
    DevicesModule,
    SmsModule,
    RegionsModule,
    DgdsModule,
    FeedbacksModule,
    UgdsModule,
    NotificationsModule,
    ReportsModule,
    LicensesModule,
    AccountsModule,
    TransactionsModule,
    LedgersModule,
    CashboxesModule,
    BillingsModule,
    StoreTypesModule,
    VersionModule,
    PdfModule,
    UgdLicensesModule,
  ],
})
export class AppModule {}
