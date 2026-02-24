import {
  Body,
  Controller,
  Get,
  HttpCode,
  Post,
  Query,
  UseGuards,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { TransactionsService } from '../domain/transactions.service';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { User } from '../../../common/decorators/user.decorator';
import { GetUsersTransactionsDto } from '../dto/get-users-transactions.dto';
import { PostTransactionDto } from '../dto/post-transaction.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { FullUrl } from '../../../common/decorators/full-url.decorator';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { PostTransferDto } from '../dto/post-transfer.dto';
import { ApiBearerAuth, ApiBody, ApiExcludeEndpoint, ApiOperation, ApiTags } from '@nestjs/swagger';
import { TransactionGuard } from '../../../common/guards/transaction.guard';

@Controller('transactions')
@ApiTags('transactions')
export class TransactionsController {
  constructor(private readonly transactionsService: TransactionsService) {}

  @Get()
  @UseGuards(AuthGuard)
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Get users all transactions',
  })
  @ApiBearerAuth()
  @ApiBody({ type: GetUsersTransactionsDto })
  async getUsersTransactions(
    @User() user: UserDao,
    @Query('page') page,
    @Query('type') type: string,
    @FullUrl() fullUrl: string,
  ) {
    return await this.transactionsService.getUsersTransactions(user, page, type, fullUrl);
  }

  @Post()
  @UseGuards(TransactionGuard)
  @UseInterceptors(TransformInterceptor)
  @UsePipes(ValidationPipe)
  @HttpCode(200)
  @ApiExcludeEndpoint()
  async postTransaction(@Body() postTransactionDto: PostTransactionDto) {
    return await this.transactionsService.postTransaction(postTransactionDto);
  }

  @Post('transfer')
  @UseInterceptors(TransformInterceptor)
  @UsePipes(ValidationPipe)
  @HttpCode(200)
  @ApiExcludeEndpoint()
  async postTransfer(@Body() postTransferDto: PostTransferDto) {
    return await this.transactionsService.postTransfer(postTransferDto);
  }
}
