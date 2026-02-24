import { Controller, Get, UseGuards, UseInterceptors } from '@nestjs/common';
import { AccountsService } from '../domain/accounts.service';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { User } from '../../../common/decorators/user.decorator';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('accounts')
@UseGuards(AuthGuard)
@UseInterceptors(TransformInterceptor)
@ApiTags('accounts')
@ApiBearerAuth()
export class AccountsController {
  constructor(private readonly accountsService: AccountsService) {}

  @Get()
  @ApiOperation({
    summary: 'Get users accounts',
  })
  async getUsersAccounts(@User() user: UserDao) {
    return await this.accountsService.getUsersAccounts(user);
  }
}
