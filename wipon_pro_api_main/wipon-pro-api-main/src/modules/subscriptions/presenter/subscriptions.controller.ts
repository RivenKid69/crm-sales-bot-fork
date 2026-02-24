import { Body, Controller, Get, Post, UseGuards, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { SubscriptionsService } from '../domain/subscriptions.service';
import { User } from '../../../common/decorators/user.decorator';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { StoreSubscriptionDto } from '../dto/store-subscription.dto';
import { ShowActiveSubscriptionDto } from '../dto/show-active-subscription.dto';
import { ShowActiveSubForErpDto } from '../dto/show-active-sub-for-erp.dto';
import { Provider } from '../../../common/decorators/provider.decorator';
import { IpFilterGuard } from '../../../common/guards/ip-filter.guard';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { BuySubscriptionDto } from '../dto/buy-subscription.dto';
import { ApiBearerAuth, ApiBody, ApiExcludeEndpoint, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { MakeRefundDto } from '../dto/make-refund.dto';

@Controller('subscription')
@UseInterceptors(TransformInterceptor)
@ApiTags('subscription')
export class SubscriptionsController {
  constructor(private readonly subscriptionService: SubscriptionsService) {}

  @Get()
  @UseGuards(AuthGuard)
  @ApiOperation({
    summary: 'Find users active subscription',
  })
  @ApiBearerAuth()
  @ApiOkResponse({
    description: 'Returns null or users active subscription',
  })
  async index(@User() user: UserDao) {
    return await this.subscriptionService.findUsersSubscription(user.id);
  }

  @Post()
  // Вот этот controller в PHP имеет путь /subscriptionS, также указан как тестовый. Непонятно...
  @UsePipes(ValidationPipe)
  @ApiExcludeEndpoint()
  async storeSubscription(@Body() storeSubscription: StoreSubscriptionDto) {
    return await this.subscriptionService.storeSubscription(storeSubscription);
  }

  @Get('active')
  @UsePipes(ValidationPipe)
  @ApiOperation({
    description: 'Only "prokassa" provider can send requests to this API',
    summary: 'Find users active subscription by phone',
  })
  @ApiOkResponse({
    description: 'Returns users active subscription id and expiration date',
  })
  @ApiBody({ type: ShowActiveSubscriptionDto })
  async showActiveSubscriptionByPhone(@Body() showActiveSubDto: ShowActiveSubscriptionDto) {
    return await this.subscriptionService.showActiveSubscriptionByPhone(showActiveSubDto);
  }

  @Get('active/erp')
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Find users active subscription by phone and bin',
  })
  @ApiOkResponse({
    description: 'Returns users active subscription id and expiration date',
  })
  @ApiBody({ type: ShowActiveSubForErpDto })
  async showActiveSubscriptionForErp(@Body() showActiveSubForErpDto: ShowActiveSubForErpDto) {
    return await this.subscriptionService.showActiveSubscriptionForErp(showActiveSubForErpDto);
  }

  @Post('buy')
  @UseGuards(AuthGuard)
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Buy subscription',
  })
  @ApiBearerAuth()
  @ApiBody({ type: BuySubscriptionDto })
  async buySubscription(@Body() buySubscriptionDto: BuySubscriptionDto, @User() user: UserDao) {
    return await this.subscriptionService.buySubscription(buySubscriptionDto, user);
  }

  @Get('all')
  @UseGuards(AuthGuard)
  @ApiOperation({
    summary: 'Get users all subscriptions (active and expired)',
  })
  @ApiBearerAuth()
  async getUsersAllSubscriptions(@User() user: UserDao) {
    return await this.subscriptionService.getUsersAllSubscriptions(user);
  }

  @Post('refund')
  @UseGuards(AuthGuard)
  @ApiOperation({
    summary: 'Make a refund of active rate (Available only in 14 days from purchase)',
  })
  @ApiBearerAuth()
  async makeRefund(@User() user: UserDao, @Body() makeRefundDto: MakeRefundDto) {
    return await this.subscriptionService.makeRefund(user, makeRefundDto);
  }
}
